"""
VideoEncoder / AudioEncoder — wrappers for obs_encoder_t.

Usage::

    venc = VideoEncoder.create("obs_x264", "h264", {"crf": 23})
    aenc = AudioEncoder.create("ffmpeg_aac", "aac", {"bitrate": 192})
"""

from __future__ import annotations

from ._ffi import ffi, get_lib, is_alive, register_wrapper
from .data import OBSData


class _BaseEncoder:
    __slots__ = ("_ptr", "_owned", "__weakref__")

    def __init__(self, ptr, *, owned: bool = True) -> None:
        if ptr == ffi.NULL:
            raise ValueError("Cannot wrap NULL obs_encoder_t pointer")
        self._ptr = ptr
        self._owned = owned
        if owned:
            register_wrapper(self)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        raw = get_lib().obs_encoder_get_name(self._ptr)
        return ffi.string(raw).decode() if raw != ffi.NULL else ""

    @name.setter
    def name(self, value: str) -> None:
        get_lib().obs_encoder_set_name(self._ptr, value.encode())

    @property
    def id(self) -> str:
        raw = get_lib().obs_encoder_get_id(self._ptr)
        return ffi.string(raw).decode() if raw != ffi.NULL else ""

    @property
    def codec(self) -> str:
        raw = get_lib().obs_encoder_get_codec(self._ptr)
        return ffi.string(raw).decode() if raw != ffi.NULL else ""

    @property
    def active(self) -> bool:
        return bool(get_lib().obs_encoder_active(self._ptr))

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def get_settings(self) -> OBSData:
        ptr = get_lib().obs_encoder_get_settings(self._ptr)
        return OBSData(_ptr=ptr, _owned=True)

    def update(self, settings: OBSData | dict) -> None:
        if isinstance(settings, dict):
            settings = OBSData(settings)
        get_lib().obs_encoder_update(self._ptr, settings._ptr)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def release(self) -> None:
        if self._ptr != ffi.NULL and self._owned and is_alive():
            get_lib().obs_encoder_release(self._ptr)
        self._ptr = ffi.NULL

    def __del__(self) -> None:
        try:
            self.release()
        except Exception:
            pass


    # ------------------------------------------------------------------
    # Region of interest (video encoders only — quality hints per region)
    # ------------------------------------------------------------------
    def add_roi(self, left: int, top: int, right: int, bottom: int,
                priority: float = 0.5) -> bool:
        """Add a region-of-interest hint to the encoder.

        priority > 0 = better quality in the region; < 0 = worse.
        Only supported by some video encoders (x264, NVENC). Returns False
        if the encoder doesn't support ROI.
        """
        roi = ffi.new("struct obs_encoder_roi *")
        roi.left, roi.top, roi.right, roi.bottom = left, top, right, bottom
        roi.priority = float(priority)
        return bool(get_lib().obs_encoder_add_roi(self._ptr, roi))

    def clear_roi(self) -> None:
        get_lib().obs_encoder_clear_roi(self._ptr)

    def has_roi(self) -> bool:
        return bool(get_lib().obs_encoder_has_roi(self._ptr))

    def get_roi_increment(self) -> int:
        return int(get_lib().obs_encoder_get_roi_increment(self._ptr))

    def list_roi(self) -> list[dict]:
        """Snapshot of every ROI currently registered with the encoder."""
        out: list[dict] = []

        @ffi.callback("void(void *, struct obs_encoder_roi *)")
        def _cb(_p, roi):
            out.append({
                "left": int(roi.left), "top": int(roi.top),
                "right": int(roi.right), "bottom": int(roi.bottom),
                "priority": float(roi.priority),
            })

        get_lib().obs_encoder_enum_roi(self._ptr, _cb, ffi.NULL)
        return out


class VideoEncoder(_BaseEncoder):
    """Wraps a video obs_encoder_t (obs_video_encoder_create).

    Auto-attaches to the global video output by default. Pass
    `attach_global=False` to defer; you can call `attach_video()` later.
    """

    @classmethod
    def create(
        cls,
        kind: str,
        name: str,
        settings: OBSData | dict | None = None,
        *,
        attach_global: bool = True,
    ) -> "VideoEncoder":
        lib = get_lib()
        if isinstance(settings, dict):
            settings = OBSData(settings)
        s_ptr = settings._ptr if settings else ffi.NULL
        ptr = lib.obs_video_encoder_create(kind.encode(), name.encode(), s_ptr, ffi.NULL)
        if ptr == ffi.NULL:
            raise RuntimeError(
                f"obs_video_encoder_create returned NULL for kind={kind!r}. "
                "Is the encoder plugin loaded?"
            )
        enc = cls(ptr)
        if attach_global:
            video = lib.obs_get_video()
            if video != ffi.NULL:
                lib.obs_encoder_set_video(ptr, video)
        return enc

    def attach_video(self, video=None) -> None:
        """Attach this encoder to the global video output (or a custom video_t*)."""
        lib = get_lib()
        if video is None:
            video = lib.obs_get_video()
        lib.obs_encoder_set_video(self._ptr, video)

    def __repr__(self) -> str:
        return f"VideoEncoder(id={self.id!r}, name={self.name!r}, codec={self.codec!r})"


class AudioEncoder(_BaseEncoder):
    """Wraps an audio obs_encoder_t (obs_audio_encoder_create).

    Auto-attaches to the global audio output by default.
    """

    @classmethod
    def create(
        cls,
        kind: str,
        name: str,
        settings: OBSData | dict | None = None,
        mixer_idx: int = 0,
        *,
        attach_global: bool = True,
    ) -> "AudioEncoder":
        lib = get_lib()
        if isinstance(settings, dict):
            settings = OBSData(settings)
        s_ptr = settings._ptr if settings else ffi.NULL
        ptr = lib.obs_audio_encoder_create(
            kind.encode(), name.encode(), s_ptr, mixer_idx, ffi.NULL
        )
        if ptr == ffi.NULL:
            raise RuntimeError(
                f"obs_audio_encoder_create returned NULL for kind={kind!r}. "
                "Is the encoder plugin loaded?"
            )
        enc = cls(ptr)
        if attach_global:
            audio = lib.obs_get_audio()
            if audio != ffi.NULL:
                lib.obs_encoder_set_audio(ptr, audio)
        return enc

    def attach_audio(self, audio=None) -> None:
        """Attach this encoder to the global audio output."""
        lib = get_lib()
        if audio is None:
            audio = lib.obs_get_audio()
        lib.obs_encoder_set_audio(self._ptr, audio)

    def __repr__(self) -> str:
        return f"AudioEncoder(id={self.id!r}, name={self.name!r}, codec={self.codec!r})"
