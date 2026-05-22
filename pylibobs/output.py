"""
Output — wrapper for obs_output_t.

Usage::

    out = Output.create("ffmpeg_muxer", "record", {"path": "rec.mkv"})
    out.set_video_encoder(venc)
    out.set_audio_encoder(aenc)
    out.start()
    ...
    out.stop()
"""

from __future__ import annotations

import time
from typing import Callable

from ._ffi import ffi, get_lib, is_alive, register_wrapper
from .data import OBSData
from .encoder import AudioEncoder, VideoEncoder
from .service import Service


class Output:
    """Wraps obs_output_t."""

    __slots__ = ("_ptr", "_owned", "_signal_callbacks", "__weakref__")

    def __init__(self, ptr, *, owned: bool = True) -> None:
        if ptr == ffi.NULL:
            raise ValueError("Cannot wrap NULL obs_output_t pointer")
        self._ptr = ptr
        self._owned = owned
        self._signal_callbacks: list = []  # keep cffi callbacks alive
        if owned:
            register_wrapper(self)

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        kind: str,
        name: str,
        settings: OBSData | dict | None = None,
    ) -> "Output":
        lib = get_lib()
        if isinstance(settings, dict):
            settings = OBSData(settings)
        s_ptr = settings._ptr if settings else ffi.NULL
        ptr = lib.obs_output_create(kind.encode(), name.encode(), s_ptr, ffi.NULL)
        if ptr == ffi.NULL:
            raise RuntimeError(
                f"obs_output_create returned NULL for kind={kind!r}. "
                "Is the output plugin loaded?"
            )
        return cls(ptr)

    # ------------------------------------------------------------------
    # Encoder / service wiring
    # ------------------------------------------------------------------

    def set_video_encoder(self, encoder: VideoEncoder) -> None:
        get_lib().obs_output_set_video_encoder(self._ptr, encoder._ptr)

    def set_audio_encoder(self, encoder: AudioEncoder, idx: int = 0) -> None:
        get_lib().obs_output_set_audio_encoder(self._ptr, encoder._ptr, idx)

    def get_video_encoder(self) -> VideoEncoder | None:
        ptr = get_lib().obs_output_get_video_encoder(self._ptr)
        if ptr == ffi.NULL:
            return None
        return VideoEncoder(ptr, owned=False)  # borrowed

    def get_audio_encoder(self, idx: int = 0) -> AudioEncoder | None:
        ptr = get_lib().obs_output_get_audio_encoder(self._ptr, idx)
        if ptr == ffi.NULL:
            return None
        return AudioEncoder(ptr, owned=False)  # borrowed

    def set_service(self, service: Service) -> None:
        get_lib().obs_output_set_service(self._ptr, service._ptr)

    def get_service(self) -> Service | None:
        ptr = get_lib().obs_output_get_service(self._ptr)
        if ptr == ffi.NULL:
            return None
        return Service(ptr, owned=False)  # borrowed

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    def start(self) -> bool:
        return bool(get_lib().obs_output_start(self._ptr))

    def stop(self, wait: bool = True, timeout: float = 10.0) -> None:
        get_lib().obs_output_stop(self._ptr)
        if wait:
            deadline = time.monotonic() + timeout
            while self.active and time.monotonic() < deadline:
                time.sleep(0.05)

    def force_stop(self) -> None:
        get_lib().obs_output_force_stop(self._ptr)

    def pause(self, paused: bool = True) -> None:
        get_lib().obs_output_pause(self._ptr, paused)

    # ------------------------------------------------------------------
    # Status / stats
    # ------------------------------------------------------------------

    @property
    def active(self) -> bool:
        return bool(get_lib().obs_output_active(self._ptr))

    @property
    def paused(self) -> bool:
        return bool(get_lib().obs_output_paused(self._ptr))

    @property
    def id(self) -> str:
        raw = get_lib().obs_output_get_id(self._ptr)
        return ffi.string(raw).decode() if raw != ffi.NULL else ""

    @property
    def name(self) -> str:
        raw = get_lib().obs_output_get_name(self._ptr)
        return ffi.string(raw).decode() if raw != ffi.NULL else ""

    @property
    def total_bytes(self) -> int:
        return int(get_lib().obs_output_get_total_bytes(self._ptr))

    @property
    def frames_dropped(self) -> int:
        return int(get_lib().obs_output_get_frames_dropped(self._ptr))

    @property
    def total_frames(self) -> int:
        return int(get_lib().obs_output_get_total_frames(self._ptr))

    @property
    def congestion(self) -> float:
        return float(get_lib().obs_output_get_congestion(self._ptr))

    # ------------------------------------------------------------------
    # Mixer track selection
    # ------------------------------------------------------------------
    @property
    def mixer(self) -> int:
        """Single-mixer mode: which audio mixer track this output uses."""
        return int(get_lib().obs_output_get_mixer(self._ptr))

    @mixer.setter
    def mixer(self, value: int) -> None:
        get_lib().obs_output_set_mixer(self._ptr, int(value))

    @property
    def mixers(self) -> int:
        """Multi-mixer mode: bitfield of mixer tracks. Bit 0 = track 1."""
        return int(get_lib().obs_output_get_mixers(self._ptr))

    @mixers.setter
    def mixers(self, bitfield: int) -> None:
        get_lib().obs_output_set_mixers(self._ptr, int(bitfield))

    # ------------------------------------------------------------------
    # Delay (for delayed broadcasts)
    # ------------------------------------------------------------------
    def set_delay(self, seconds: int, flags: int = 0) -> None:
        """Configure a fixed delay for this output.
        flags: 0=normal, 1=preserve_delay (keep on reconnect)."""
        get_lib().obs_output_set_delay(self._ptr, int(seconds), int(flags))

    @property
    def delay(self) -> int:
        return int(get_lib().obs_output_get_delay(self._ptr))

    @property
    def active_delay(self) -> int:
        """Currently-buffered delay in seconds."""
        return int(get_lib().obs_output_get_active_delay(self._ptr))

    # ------------------------------------------------------------------
    # Reconnect settings (streaming only)
    # ------------------------------------------------------------------
    def set_reconnect_settings(self, retry_count: int = 20, retry_sec: int = 10) -> None:
        get_lib().obs_output_set_reconnect_settings(self._ptr,
                                                    int(retry_count),
                                                    int(retry_sec))

    @property
    def reconnecting(self) -> bool:
        return bool(get_lib().obs_output_reconnecting(self._ptr))

    # ------------------------------------------------------------------
    # Capabilities
    # ------------------------------------------------------------------
    @property
    def can_pause(self) -> bool:
        return bool(get_lib().obs_output_can_pause(self._ptr))

    @property
    def flags(self) -> int:
        """obs_output_flags bitfield: VIDEO=1, AUDIO=2, AV=3, ENCODED=4,
        SERVICE=8, MULTI_TRACK=16, CAN_PAUSE=32."""
        return int(get_lib().obs_output_get_flags(self._ptr))

    # ------------------------------------------------------------------
    # Encoded packet callback — get each packet as it's encoded
    # ------------------------------------------------------------------
    def add_packet_callback(self, fn):
        """Register fn(packet_dict) called for every encoded packet.

        packet_dict contains: data (bytes), pts, dts, type (0=audio, 1=video),
        keyframe, track_idx, timebase (num, den).
        """
        lib = get_lib()

        @ffi.callback("void(void *, struct encoder_packet *)")
        def _trampoline(_p, packet):
            try:
                size = int(packet.size)
                fn({
                    "data":     bytes(ffi.buffer(packet.data, size)) if packet.data != ffi.NULL else b"",
                    "size":     size,
                    "pts":      int(packet.pts),
                    "dts":      int(packet.dts),
                    "timebase": (int(packet.timebase_num), int(packet.timebase_den)),
                    "type":     int(packet.type),
                    "keyframe": bool(packet.keyframe),
                    "track_idx": int(packet.track_idx),
                })
            except Exception:
                pass

        self._signal_callbacks.append(_trampoline)
        lib.obs_output_add_packet_callback(self._ptr, _trampoline, ffi.NULL)
        return _trampoline

    def remove_packet_callback(self, handle) -> None:
        get_lib().obs_output_remove_packet_callback(self._ptr, handle, ffi.NULL)
        if handle in self._signal_callbacks:
            self._signal_callbacks.remove(handle)

    @property
    def last_error(self) -> str | None:
        raw = get_lib().obs_output_get_last_error(self._ptr)
        if raw == ffi.NULL:
            return None
        return ffi.string(raw).decode()

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def get_settings(self) -> OBSData:
        ptr = get_lib().obs_output_get_settings(self._ptr)
        return OBSData(_ptr=ptr, _owned=True)

    def update(self, settings: OBSData | dict) -> None:
        if isinstance(settings, dict):
            settings = OBSData(settings)
        get_lib().obs_output_update(self._ptr, settings._ptr)

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    def connect_signal(self, signal: str, callback: Callable[[dict], None]) -> None:
        """
        Connect a Python callable to an output signal.

        The callable receives a dict with whatever calldata the signal provides.
        Common signals: "start", "stop", "starting", "stopping", "activate",
                        "deactivate", "reconnect", "reconnect_success".
        """
        lib = get_lib()
        handler = lib.obs_output_get_signal_handler(self._ptr)

        @ffi.callback("void(void *, calldata_t *)")
        def _cb(_data, _cd):
            try:
                callback({})
            except Exception:
                pass

        self._signal_callbacks.append(_cb)
        lib.signal_handler_connect(handler, signal.encode(), _cb, ffi.NULL)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def release(self) -> None:
        if self._ptr != ffi.NULL and self._owned and is_alive():
            lib = get_lib()
            # Force-stop in case the user forgot — releasing an active output
            # while libobs walks its outputs list crashes the shutdown path.
            if lib.obs_output_active(self._ptr):
                lib.obs_output_force_stop(self._ptr)
            lib.obs_output_release(self._ptr)
        # Drop callbacks AFTER release so libobs has finished using them.
        self._signal_callbacks = []
        self._ptr = ffi.NULL

    def __del__(self) -> None:
        try:
            self.release()
        except Exception:
            pass

    def __repr__(self) -> str:
        return f"Output(id={self.id!r}, name={self.name!r}, active={self.active})"
