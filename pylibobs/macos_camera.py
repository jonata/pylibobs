"""Feed a macOS CoreMediaIO output stream from libobs's main composition.

The camera extension must already be installed and enabled by its vendor.
This module neither installs a device nor loads a vendor's frontend plugin.
Only a device UID crosses this API; no GUI toolkit or application rules apply.
"""
from __future__ import annotations

import ctypes
from functools import lru_cache
from pathlib import Path
import platform
import threading

_outputs: set[CameraOutput] = set()
_device_uids: set[str] = set()
_outputs_lock = threading.Lock()


@lru_cache(maxsize=1)
def _native():
    if platform.system() != "Darwin":
        raise OSError("CoreMediaIO camera output requires macOS")
    library = ctypes.CDLL(str(Path(__file__).parent / "native/macos_camera.dylib"))
    signatures = {
        "pyc_camera_create": ([ctypes.c_char_p, ctypes.c_uint32, ctypes.c_uint32,
                               ctypes.c_uint32, ctypes.c_uint32, ctypes.POINTER(ctypes.c_int32)], ctypes.c_void_p),
        "pyc_camera_write": ([ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32,
                              ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint64], ctypes.c_int),
        "pyc_camera_consumed": ([ctypes.c_void_p], ctypes.c_uint64),
        "pyc_camera_error": ([ctypes.c_void_p], ctypes.c_int32),
        "pyc_camera_close": ([ctypes.c_void_p], ctypes.c_int32),
    }
    for name, (arguments, result) in signatures.items():
        function = getattr(library, name)
        function.argtypes, function.restype = arguments, result
    return library


class CameraOutput:
    """Bounded NV12 delivery to an existing CoreMediaIO camera sink.

    Initialize OBS video first, then construct with the destination's native
    device UID. The destination must accept dynamically described NV12 frames
    and must not be used by another producer. CoreMediaIO extensions arbitrate
    access; some extensions permit competing writers without reporting busy.
    The main mix is converted by libobs to limited-range Rec.709
    NV12, copied directly from borrowed native planes into IOSurface-backed
    pixel buffers, and transferred by CoreMediaIO. No frame bytes cross Python.
    Queue/pixel-buffer capacity is bounded; a slow consumer drops new frames.
    ``frames_consumed`` proves the camera service drained frames, independently
    of whether a capture application has opened the camera's source stream.
    Close before shutting down OBS; active callbacks retain their owner until
    explicit close or registry-managed context teardown.
    Close before changing OBS video settings, then construct a new output;
    active video consumers prevent libobs video reset.
    """

    def __init__(self, device_uid: str):
        if not isinstance(device_uid, str) or not device_uid or "\0" in device_uid or len(device_uid) > 1024:
            raise ValueError("Expected a nonempty native camera device UID")
        from ._ffi import ffi, get_lib

        self._ffi, self._lib = ffi, get_lib()
        self._library = _native()
        self._lifecycle_lock = threading.RLock()
        self._frame_lock = threading.Lock()
        self._pointer = None
        self._callback = None
        self._close_failed = False
        self._owns_device_uid = False
        self.frames_published = 0
        self.frames_dropped = 0
        self.last_error = ""
        self.device_uid = device_uid
        info = ffi.new("struct obs_video_info *")
        if not self._lib.obs_get_video_info(info):
            raise RuntimeError("Initialize OBS video before creating a camera output")
        width, height = int(info.output_width), int(info.output_height)
        if width % 2 or height % 2:
            raise ValueError("NV12 camera output requires even output dimensions")
        with _outputs_lock:
            if device_uid in _device_uids:
                raise RuntimeError("This process already owns the camera output stream")
            _device_uids.add(device_uid)
            self._owns_device_uid = True
        try:
            self._connect(width, height, int(info.fps_num), int(info.fps_den))
        except BaseException:
            self.close()
            raise

    def _connect(self, width: int, height: int, fps_num: int, fps_den: int) -> None:
        from ._ffi import register_wrapper
        from .context import ColorSpace, VideoFormat, VideoRange

        ffi = self._ffi
        error = ctypes.c_int32()
        self._pointer = self._library.pyc_camera_create(
            self.device_uid.encode(), width, height, fps_num, fps_den, ctypes.byref(error))
        if not self._pointer:
            raise OSError(error.value, "Unable to open CoreMediaIO camera output stream")
        conversion = ffi.new("struct video_scale_info *", {
            "format": int(VideoFormat.NV12), "width": width, "height": height,
            "range": int(VideoRange.PARTIAL), "colorspace": int(ColorSpace.CS709),
        })

        @ffi.callback("raw_video_callback_t")
        def frame_callback(_parameter, frame):
            with self._frame_lock:
                if not self._pointer or self.last_error:
                    return
                try:
                    result = self._library.pyc_camera_write(self._pointer,
                        int(ffi.cast("uintptr_t", frame.data[0])), int(frame.linesize[0]),
                        int(ffi.cast("uintptr_t", frame.data[1])), int(frame.linesize[1]), int(frame.timestamp))
                    if result < 0:
                        self.last_error = f"CoreMediaIO camera frame rejected: {self._library.pyc_camera_error(self._pointer)}"
                    else:
                        self.frames_published += result
                        self.frames_dropped += not result
                except Exception as error:  # Native video thread must not unwind through C.
                    self.last_error = str(error)

        self._lib.obs_add_raw_video_callback(conversion, frame_callback, ffi.NULL)
        self._callback = frame_callback
        register_wrapper(self)
        # C retains only a function pointer. Retain its Python owner until
        # explicit close or context-managed registry teardown.
        with _outputs_lock:
            _outputs.add(self)

    @property
    def active(self) -> bool:
        return bool(self._pointer) and not self.last_error

    @property
    def frames_consumed(self) -> int:
        with self._frame_lock:
            return int(self._library.pyc_camera_consumed(self._pointer)) if self._pointer else 0

    def close(self) -> None:
        with self._lifecycle_lock:
            callback = self._callback
            if callback is not None:
                # Removal waits for callbacks: never hold their frame lock here.
                self._lib.obs_remove_raw_video_callback(callback, self._ffi.NULL)
                self._callback = None
            with self._frame_lock:
                pointer, self._pointer = self._pointer, None
                if pointer:
                    status = self._library.pyc_camera_close(pointer)
                    if status:
                        self.last_error = f"CoreMediaIO camera close failed: {status}"
                        self._close_failed = True
            with _outputs_lock:
                _outputs.discard(self)
                # A failed native stop cannot prove this client's old stream
                # ended. Refuse another local writer until its process exits.
                if self._owns_device_uid and not self._close_failed:
                    _device_uids.discard(self.device_uid)
                    self._owns_device_uid = False

    def release(self) -> None:
        self.close()

    def __enter__(self):
        return self

    def __exit__(self, *_arguments):
        self.close()
