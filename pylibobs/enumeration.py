"""
Enumeration — list-everything queries against the running libobs instance.

Includes:
  * Live-object enumeration  (enum_sources, enum_scenes, enum_all_sources)
  * Type-id enumeration       (enum_source_types, enum_input_types,
                               enum_filter_types, enum_transition_types,
                               enum_encoder_types, enum_output_types,
                               enum_service_types)
  * Display-name lookup       (get_display_name_for)
  * Default-settings lookup   (get_defaults_for)
  * Audio monitoring devices  (enum_audio_monitoring_devices)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ._ffi import ffi, get_lib
from .data import OBSData


# ---------------------------------------------------------------------------
# Internal helper for type-id enumerators that follow the (idx, **id) pattern
# ---------------------------------------------------------------------------
def _enum_string_ids(fn) -> list[str]:
    out: list[str] = []
    idx = 0
    holder = ffi.new("const char **")
    while fn(idx, holder):
        if holder[0] != ffi.NULL:
            out.append(ffi.string(holder[0]).decode())
        idx += 1
    return out


def enum_source_types() -> list[str]:
    """All registered source type ids (filters + transitions + inputs)."""
    return _enum_string_ids(get_lib().obs_enum_source_types)


def enum_input_types() -> list[str]:
    """Source types that are *inputs* (color_source, monitor_capture, ...)."""
    return _enum_string_ids(get_lib().obs_enum_input_types)


@dataclass(frozen=True)
class InputType:
    id: str            # versioned id, e.g. "color_source_v3"
    unversioned_id: str  # stable id, e.g. "color_source"


def enum_input_types2() -> list[InputType]:
    """Enumerate input types with both their versioned and unversioned ids."""
    lib = get_lib()
    out: list[InputType] = []
    idx = 0
    a = ffi.new("const char **")
    b = ffi.new("const char **")
    while lib.obs_enum_input_types2(idx, a, b):
        idv = ffi.string(a[0]).decode() if a[0] != ffi.NULL else ""
        unv = ffi.string(b[0]).decode() if b[0] != ffi.NULL else ""
        out.append(InputType(id=idv, unversioned_id=unv))
        idx += 1
    return out


def enum_filter_types() -> list[str]:
    return _enum_string_ids(get_lib().obs_enum_filter_types)


def enum_transition_types() -> list[str]:
    return _enum_string_ids(get_lib().obs_enum_transition_types)


def enum_encoder_types() -> list[str]:
    return _enum_string_ids(get_lib().obs_enum_encoder_types)


def enum_output_types() -> list[str]:
    return _enum_string_ids(get_lib().obs_enum_output_types)


def enum_service_types() -> list[str]:
    return _enum_string_ids(get_lib().obs_enum_service_types)


# ---------------------------------------------------------------------------
# Live object enumeration — these walk the runtime, not the registry
# ---------------------------------------------------------------------------

def _collect_sources(walker) -> list:
    """Walk an enum_* callback and return strong-ref Source wrappers.

    libobs gives the callback a *borrowed* pointer that's only valid for the
    duration of the walk. We must promote each via obs_source_get_ref() to
    keep it valid. To avoid an iteration-time heap churn that has been
    observed to destabilise libobs across many startup/shutdown cycles in
    tests, we first collect borrowed pointers into a list, then promote
    them after the walk completes.
    """
    from .source import Source
    lib = get_lib()
    borrowed_ptrs: list = []

    @ffi.callback("bool(void *, obs_source_t *)")
    def _cb(_data, src_ptr):
        if src_ptr != ffi.NULL:
            borrowed_ptrs.append(src_ptr)
        return True

    walker(_cb, ffi.NULL)

    # Promote outside the callback. Some pointers may be mid-destruction
    # (get_ref returns NULL) — skip those.
    out: list[Source] = []
    for ptr in borrowed_ptrs:
        strong = lib.obs_source_get_ref(ptr)
        if strong != ffi.NULL:
            out.append(Source(strong, owned=True))
    return out


def enum_sources():
    """All live inputs (filters & transitions excluded)."""
    return _collect_sources(get_lib().obs_enum_sources)


def enum_scenes():
    """All live scene sources."""
    from .scene import Scene
    lib = get_lib()
    sources = _collect_sources(lib.obs_enum_scenes)
    # Re-wrap as Scene wrappers (sources already hold strong refs)
    scenes = []
    for s in sources:
        scene_ptr = lib.obs_scene_from_source(s._ptr)
        if scene_ptr != ffi.NULL:
            strong = lib.obs_scene_get_ref(scene_ptr)
            if strong != ffi.NULL:
                sc = Scene.__new__(Scene)
                sc._ptr = strong
                sc._owned = True
                from ._ffi import register_wrapper
                register_wrapper(sc)
                scenes.append(sc)
    return scenes


def enum_all_sources():
    """Every live source, including filters and transitions."""
    return _collect_sources(get_lib().obs_enum_all_sources)


# ---------------------------------------------------------------------------
# Display name + defaults lookup
# ---------------------------------------------------------------------------

def get_source_display_name(source_id: str) -> str:
    raw = get_lib().obs_source_get_display_name(source_id.encode())
    return ffi.string(raw).decode() if raw != ffi.NULL else ""


def get_output_display_name(output_id: str) -> str:
    raw = get_lib().obs_output_get_display_name(output_id.encode())
    return ffi.string(raw).decode() if raw != ffi.NULL else ""


def get_encoder_display_name(encoder_id: str) -> str:
    raw = get_lib().obs_encoder_get_display_name(encoder_id.encode())
    return ffi.string(raw).decode() if raw != ffi.NULL else ""


def get_service_display_name(service_id: str) -> str:
    raw = get_lib().obs_service_get_display_name(service_id.encode())
    return ffi.string(raw).decode() if raw != ffi.NULL else ""


def get_source_defaults(source_id: str) -> OBSData | None:
    ptr = get_lib().obs_get_source_defaults(source_id.encode())
    if ptr == ffi.NULL:
        return None
    return OBSData(_ptr=ptr, _owned=True)


def get_encoder_defaults(encoder_id: str) -> OBSData | None:
    ptr = get_lib().obs_encoder_defaults(encoder_id.encode())
    if ptr == ffi.NULL:
        return None
    return OBSData(_ptr=ptr, _owned=True)


def get_service_defaults(service_id: str) -> OBSData | None:
    ptr = get_lib().obs_service_defaults(service_id.encode())
    if ptr == ffi.NULL:
        return None
    return OBSData(_ptr=ptr, _owned=True)


def get_output_defaults(output_id: str) -> OBSData | None:
    ptr = get_lib().obs_output_defaults(output_id.encode())
    if ptr == ffi.NULL:
        return None
    return OBSData(_ptr=ptr, _owned=True)


# ---------------------------------------------------------------------------
# Audio monitoring devices
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AudioMonitoringDevice:
    name: str   # human-readable name
    id: str     # OS-specific id used by obs_set_audio_monitoring_device


def enum_audio_monitoring_devices() -> list[AudioMonitoringDevice]:
    lib = get_lib()
    out: list[AudioMonitoringDevice] = []

    @ffi.callback("bool(void *, const char *, const char *)")
    def _cb(_data, name, dev_id):
        try:
            n = ffi.string(name).decode() if name != ffi.NULL else ""
            i = ffi.string(dev_id).decode() if dev_id != ffi.NULL else ""
            out.append(AudioMonitoringDevice(name=n, id=i))
        except Exception:
            pass
        return True

    lib.obs_enum_audio_monitoring_devices(_cb, ffi.NULL)
    return out


def audio_monitoring_available() -> bool:
    return bool(get_lib().obs_audio_monitoring_available())


def set_audio_monitoring_device(name: str, dev_id: str) -> bool:
    return bool(get_lib().obs_set_audio_monitoring_device(name.encode(),
                                                          dev_id.encode()))


def get_audio_monitoring_device() -> tuple[str, str]:
    name_h = ffi.new("const char **")
    id_h = ffi.new("const char **")
    get_lib().obs_get_audio_monitoring_device(name_h, id_h)
    name = ffi.string(name_h[0]).decode() if name_h[0] != ffi.NULL else ""
    dev_id = ffi.string(id_h[0]).decode() if id_h[0] != ffi.NULL else ""
    return name, dev_id
