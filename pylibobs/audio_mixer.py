"""
VolumeMeter + Fader — the building blocks of an OBS-like audio mixer panel.

VolumeMeter
    Reports real-time per-channel magnitude/peak levels. Wire one to each
    audio source you want to visualise. A Python callback receives the
    levels every ~30 ms (libobs's mixing rate).

Fader
    A logarithmic / cubic / IEC volume slider. Attach to a source to control
    its volume; reads/writes are in dB or 0..1 deflection.
"""

from __future__ import annotations

import threading
from enum import IntEnum
from typing import Callable

from ._ffi import ffi, get_lib, is_alive, register_wrapper
from .source import Source

# libobs MAX_AUDIO_CHANNELS = 8
_MAX_CHANNELS = 8


class PeakMeterType(IntEnum):
    SAMPLE_PEAK = 0
    TRUE_PEAK   = 1


class FaderType(IntEnum):
    CUBIC = 0
    IEC   = 1   # IEC 60268-18, the standard "dB" curve
    LOG   = 2


# ==========================================================================
# VolumeMeter
# ==========================================================================
class VolumeMeter:
    """Wraps obs_volmeter_t."""

    __slots__ = ("_ptr", "_owned", "_cbs", "_attached_source", "__weakref__")

    def __init__(self, ptr, *, owned: bool = True) -> None:
        if ptr == ffi.NULL:
            raise ValueError("Cannot wrap NULL obs_volmeter_t pointer")
        self._ptr = ptr
        self._owned = owned
        self._cbs: list = []   # keep cffi callbacks alive
        self._attached_source = None
        if owned:
            register_wrapper(self)

    @classmethod
    def create(cls, peak_type: PeakMeterType = PeakMeterType.SAMPLE_PEAK) -> "VolumeMeter":
        ptr = get_lib().obs_volmeter_create(int(peak_type))
        if ptr == ffi.NULL:
            raise RuntimeError("obs_volmeter_create returned NULL")
        return cls(ptr)

    # ------------------------------------------------------------------
    # Source binding
    # ------------------------------------------------------------------

    def attach(self, source: Source) -> None:
        if not get_lib().obs_volmeter_attach_source(self._ptr, source._ptr):
            raise RuntimeError("obs_volmeter_attach_source returned false")
        self._attached_source = source

    def detach(self) -> None:
        get_lib().obs_volmeter_detach_source(self._ptr)
        self._attached_source = None

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def set_peak_meter_type(self, type_: PeakMeterType) -> None:
        get_lib().obs_volmeter_set_peak_meter_type(self._ptr, int(type_))

    @property
    def channel_count(self) -> int:
        return int(get_lib().obs_volmeter_get_nr_channels(self._ptr))

    # ------------------------------------------------------------------
    # Callbacks — fired on libobs's audio thread; do minimal work
    # ------------------------------------------------------------------

    def add_callback(
        self,
        fn: Callable[[list[float], list[float], list[float]], None],
    ) -> None:
        """Register a Python callable to receive (magnitude, peak, input_peak)
        lists, each `MAX_AUDIO_CHANNELS` floats long (8). Units are dBFS;
        -INFINITY for silence."""
        lib = get_lib()

        @ffi.callback("void(void *, const float *, const float *, const float *)")
        def _cb(_param, mag_ptr, peak_ptr, input_peak_ptr):
            try:
                mag = [float(mag_ptr[i]) for i in range(_MAX_CHANNELS)]
                pk  = [float(peak_ptr[i]) for i in range(_MAX_CHANNELS)]
                ip  = [float(input_peak_ptr[i]) for i in range(_MAX_CHANNELS)]
                fn(mag, pk, ip)
            except Exception:
                pass  # swallow — we're on libobs's audio thread

        self._cbs.append(_cb)
        lib.obs_volmeter_add_callback(self._ptr, _cb, ffi.NULL)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def release(self) -> None:
        if self._ptr != ffi.NULL and self._owned and is_alive():
            lib = get_lib()
            for cb in self._cbs:
                try: lib.obs_volmeter_remove_callback(self._ptr, cb, ffi.NULL)
                except Exception: pass
            try: lib.obs_volmeter_detach_source(self._ptr)
            except Exception: pass
            lib.obs_volmeter_destroy(self._ptr)
        self._cbs = []
        self._attached_source = None
        self._ptr = ffi.NULL

    def __del__(self) -> None:
        try: self.release()
        except Exception: pass


# ==========================================================================
# Fader
# ==========================================================================
class Fader:
    """Wraps obs_fader_t — a calibrated volume slider for a source."""

    __slots__ = ("_ptr", "_owned", "_cbs", "_attached_source", "__weakref__")

    def __init__(self, ptr, *, owned: bool = True) -> None:
        if ptr == ffi.NULL:
            raise ValueError("Cannot wrap NULL obs_fader_t pointer")
        self._ptr = ptr
        self._owned = owned
        self._cbs: list = []
        self._attached_source = None
        if owned:
            register_wrapper(self)

    @classmethod
    def create(cls, fader_type: FaderType = FaderType.IEC) -> "Fader":
        ptr = get_lib().obs_fader_create(int(fader_type))
        if ptr == ffi.NULL:
            raise RuntimeError("obs_fader_create returned NULL")
        return cls(ptr)

    # ------------------------------------------------------------------
    # Source binding
    # ------------------------------------------------------------------

    def attach(self, source: Source) -> None:
        if not get_lib().obs_fader_attach_source(self._ptr, source._ptr):
            raise RuntimeError("obs_fader_attach_source returned false")
        self._attached_source = source

    def detach(self) -> None:
        get_lib().obs_fader_detach_source(self._ptr)
        self._attached_source = None

    # ------------------------------------------------------------------
    # Levels
    # ------------------------------------------------------------------

    @property
    def db(self) -> float:
        return float(get_lib().obs_fader_get_db(self._ptr))

    @db.setter
    def db(self, value: float) -> None:
        get_lib().obs_fader_set_db(self._ptr, float(value))

    @property
    def deflection(self) -> float:
        """Slider position in [0.0, 1.0]. Convenient for GUI sliders."""
        return float(get_lib().obs_fader_get_deflection(self._ptr))

    @deflection.setter
    def deflection(self, value: float) -> None:
        get_lib().obs_fader_set_deflection(self._ptr, float(value))

    @property
    def mul(self) -> float:
        """Linear multiplier (1.0 = unity gain)."""
        return float(get_lib().obs_fader_get_mul(self._ptr))

    @mul.setter
    def mul(self, value: float) -> None:
        get_lib().obs_fader_set_mul(self._ptr, float(value))

    def db_to_deflection(self, db: float) -> float:
        """Convert a dB value to a [0..1] deflection on this fader's curve.

        Implemented in Python via the get/set pair instead of
        obs_fader_db_to_def(), because the latter returns junk in some libobs
        builds (likely a signature mismatch with this OBS version's export).
        """
        saved = self.db
        try:
            self.db = float(db)
            return self.deflection
        finally:
            self.db = saved

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def add_callback(self, fn: Callable[[float], None]) -> None:
        """Register a callback that fires whenever the fader's dB value changes."""
        lib = get_lib()

        @ffi.callback("void(void *, float)")
        def _cb(_param, db):
            try:
                fn(float(db))
            except Exception:
                pass

        self._cbs.append(_cb)
        lib.obs_fader_add_callback(self._ptr, _cb, ffi.NULL)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def release(self) -> None:
        if self._ptr != ffi.NULL and self._owned and is_alive():
            lib = get_lib()
            for cb in self._cbs:
                try: lib.obs_fader_remove_callback(self._ptr, cb, ffi.NULL)
                except Exception: pass
            try: lib.obs_fader_detach_source(self._ptr)
            except Exception: pass
            lib.obs_fader_destroy(self._ptr)
        self._cbs = []
        self._attached_source = None
        self._ptr = ffi.NULL

    def __del__(self) -> None:
        try: self.release()
        except Exception: pass
