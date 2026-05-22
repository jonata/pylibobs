"""
Source — wrapper for obs_source_t.

OBS 32+ removed `obs_source_addref`. Reference counting is now ownership-based:
  - Strong (owned) refs are returned by `obs_source_create*` and `obs_get_source_by_name`.
    These MUST be released exactly once.
  - Borrowed refs are returned by `obs_scene_get_source`, `obs_sceneitem_get_source`,
    `obs_output_get_video_encoder`, etc. These MUST NOT be released.
"""

from __future__ import annotations

from ._ffi import ffi, get_lib, is_alive, register_wrapper
from .data import OBSData


class Source:
    """Wraps obs_source_t. Use the right constructor for owned vs. borrowed refs."""

    __slots__ = ("_ptr", "_owned", "__weakref__")

    def __init__(self, ptr, *, owned: bool = True) -> None:
        if ptr == ffi.NULL:
            raise ValueError("Cannot wrap NULL obs_source_t pointer")
        self._ptr = ptr
        self._owned = owned
        if owned:
            register_wrapper(self)

    # ------------------------------------------------------------------
    # Factory methods
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        kind: str,
        name: str,
        settings: OBSData | dict | None = None,
    ) -> "Source":
        lib = get_lib()
        if isinstance(settings, dict):
            settings = OBSData(settings)
        s_ptr = settings._ptr if settings else ffi.NULL
        ptr = lib.obs_source_create(kind.encode(), name.encode(), s_ptr, ffi.NULL)
        if ptr == ffi.NULL:
            raise RuntimeError(
                f"obs_source_create returned NULL for kind={kind!r}, name={name!r}. "
                "Is the plugin loaded? Check obs.load_modules()."
            )
        return cls(ptr, owned=True)

    @classmethod
    def create_private(
        cls,
        kind: str,
        name: str,
        settings: OBSData | dict | None = None,
    ) -> "Source":
        lib = get_lib()
        if isinstance(settings, dict):
            settings = OBSData(settings)
        s_ptr = settings._ptr if settings else ffi.NULL
        ptr = lib.obs_source_create_private(kind.encode(), name.encode(), s_ptr)
        if ptr == ffi.NULL:
            raise RuntimeError(f"obs_source_create_private returned NULL for kind={kind!r}")
        return cls(ptr, owned=True)

    @classmethod
    def get_by_name(cls, name: str) -> "Source | None":
        lib = get_lib()
        ptr = lib.obs_get_source_by_name(name.encode())
        return cls(ptr, owned=True) if ptr != ffi.NULL else None

    @classmethod
    def borrow(cls, ptr) -> "Source":
        """Wrap a borrowed pointer (will NOT release on __del__)."""
        return cls(ptr, owned=False)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        raw = get_lib().obs_source_get_name(self._ptr)
        return ffi.string(raw).decode() if raw != ffi.NULL else ""

    @name.setter
    def name(self, value: str) -> None:
        get_lib().obs_source_set_name(self._ptr, value.encode())

    @property
    def id(self) -> str:
        raw = get_lib().obs_source_get_id(self._ptr)
        return ffi.string(raw).decode() if raw != ffi.NULL else ""

    @property
    def uuid(self) -> str:
        raw = get_lib().obs_source_get_uuid(self._ptr)
        return ffi.string(raw).decode() if raw != ffi.NULL else ""

    @property
    def width(self) -> int:
        return int(get_lib().obs_source_get_width(self._ptr))

    @property
    def height(self) -> int:
        return int(get_lib().obs_source_get_height(self._ptr))

    @property
    def enabled(self) -> bool:
        return bool(get_lib().obs_source_enabled(self._ptr))

    @enabled.setter
    def enabled(self, value: bool) -> None:
        get_lib().obs_source_set_enabled(self._ptr, value)

    @property
    def muted(self) -> bool:
        return bool(get_lib().obs_source_muted(self._ptr))

    @muted.setter
    def muted(self, value: bool) -> None:
        get_lib().obs_source_set_muted(self._ptr, value)

    @property
    def volume(self) -> float:
        return float(get_lib().obs_source_get_volume(self._ptr))

    @volume.setter
    def volume(self, value: float) -> None:
        get_lib().obs_source_set_volume(self._ptr, float(value))

    # ------------------------------------------------------------------
    # Active / showing — render-state introspection
    # ------------------------------------------------------------------
    @property
    def active(self) -> bool:
        return bool(get_lib().obs_source_active(self._ptr))

    @property
    def showing(self) -> bool:
        return bool(get_lib().obs_source_showing(self._ptr))

    # ------------------------------------------------------------------
    # Audio fine controls
    # ------------------------------------------------------------------
    @property
    def balance(self) -> float:
        """Stereo balance, 0.0=left .. 1.0=right (0.5=center)."""
        return float(get_lib().obs_source_get_balance_value(self._ptr))

    @balance.setter
    def balance(self, value: float) -> None:
        get_lib().obs_source_set_balance_value(self._ptr, float(value))

    @property
    def sync_offset(self) -> int:
        """Audio sync offset in nanoseconds (positive = delay audio)."""
        return int(get_lib().obs_source_get_sync_offset(self._ptr))

    @sync_offset.setter
    def sync_offset(self, ns: int) -> None:
        get_lib().obs_source_set_sync_offset(self._ptr, int(ns))

    @property
    def audio_active(self) -> bool:
        """Whether this source's audio is currently routed to mixers."""
        return bool(get_lib().obs_source_audio_active(self._ptr))

    @audio_active.setter
    def audio_active(self, value: bool) -> None:
        get_lib().obs_source_set_audio_active(self._ptr, bool(value))

    @property
    def audio_mixers(self) -> int:
        """Bitfield of mixer tracks (bit 0 = track 1)."""
        return int(get_lib().obs_source_get_audio_mixers(self._ptr))

    @audio_mixers.setter
    def audio_mixers(self, bitfield: int) -> None:
        get_lib().obs_source_set_audio_mixers(self._ptr, int(bitfield))

    # ------------------------------------------------------------------
    # Deinterlace
    # ------------------------------------------------------------------
    @property
    def deinterlace_mode(self) -> int:
        return int(get_lib().obs_source_get_deinterlace_mode(self._ptr))

    @deinterlace_mode.setter
    def deinterlace_mode(self, value: int) -> None:
        get_lib().obs_source_set_deinterlace_mode(self._ptr, int(value))

    @property
    def deinterlace_field_order(self) -> int:
        return int(get_lib().obs_source_get_deinterlace_field_order(self._ptr))

    @deinterlace_field_order.setter
    def deinterlace_field_order(self, value: int) -> None:
        get_lib().obs_source_set_deinterlace_field_order(self._ptr, int(value))

    # ------------------------------------------------------------------
    # Media playback (works on ffmpeg_source, vlc_source, etc.)
    # ------------------------------------------------------------------
    def media_play_pause(self, pause: bool = True) -> None:
        get_lib().obs_source_media_play_pause(self._ptr, bool(pause))

    def media_restart(self) -> None:
        get_lib().obs_source_media_restart(self._ptr)

    def media_stop(self) -> None:
        get_lib().obs_source_media_stop(self._ptr)

    def media_next(self) -> None:
        get_lib().obs_source_media_next(self._ptr)

    def media_previous(self) -> None:
        get_lib().obs_source_media_previous(self._ptr)

    @property
    def media_duration(self) -> int:
        """Total duration of the current media in milliseconds (-1 if unknown)."""
        return int(get_lib().obs_source_media_get_duration(self._ptr))

    @property
    def media_time(self) -> int:
        """Current playback position in milliseconds."""
        return int(get_lib().obs_source_media_get_time(self._ptr))

    @media_time.setter
    def media_time(self, ms: int) -> None:
        get_lib().obs_source_media_set_time(self._ptr, int(ms))

    @property
    def media_state(self) -> int:
        """0 None, 1 Playing, 2 Opening, 3 Buffering, 4 Paused, 5 Stopped,
        6 Ended, 7 Error."""
        return int(get_lib().obs_source_media_get_state(self._ptr))

    # ------------------------------------------------------------------
    # Private settings (per-source state not in public settings)
    # ------------------------------------------------------------------
    def get_private_settings(self) -> OBSData:
        ptr = get_lib().obs_source_get_private_settings(self._ptr)
        return OBSData(_ptr=ptr, _owned=True)

    # ------------------------------------------------------------------
    # Recursive enumeration of children (scenes, transitions, groups)
    # ------------------------------------------------------------------
    def enum_active_sources(self) -> list["Source"]:
        return self._enum_helper(get_lib().obs_source_enum_active_sources)

    def enum_active_tree(self) -> list["Source"]:
        return self._enum_helper(get_lib().obs_source_enum_active_tree)

    def enum_full_tree(self) -> list["Source"]:
        return self._enum_helper(get_lib().obs_source_enum_full_tree)

    def _enum_helper(self, walker) -> list["Source"]:
        lib = get_lib()
        collected: list[Source] = []

        @ffi.callback("void(obs_source_t *, obs_source_t *, void *)")
        def _cb(_parent, child, _param):
            if child == ffi.NULL:
                return
            strong = lib.obs_source_get_ref(child)
            if strong != ffi.NULL:
                collected.append(Source(strong, owned=True))

        walker(self._ptr, _cb, ffi.NULL)
        return collected

    # ------------------------------------------------------------------
    # Filter copy
    # ------------------------------------------------------------------
    def copy_filters_to(self, dst: "Source") -> None:
        """Copy ALL filters from self to dst."""
        get_lib().obs_source_copy_filters(dst._ptr, self._ptr)

    def copy_single_filter_to(self, filter_obj, dst: "Source") -> bool:
        """Copy one specific filter from self to dst."""
        return bool(get_lib().obs_source_copy_single_filter(dst._ptr, filter_obj._ptr))

    # ------------------------------------------------------------------
    # Settings / properties
    # ------------------------------------------------------------------

    def get_settings(self) -> OBSData:
        ptr = get_lib().obs_source_get_settings(self._ptr)
        return OBSData(_ptr=ptr, _owned=True)

    def get_properties(self):
        """Return the source's configurable properties as a Properties object.

        Lets you enumerate list-type properties (like `monitor_id` or
        `window`) and discover their valid values dynamically.
        """
        from .properties import Properties
        return Properties.from_source(self)

    def update(self, settings: OBSData | dict) -> None:
        if isinstance(settings, dict):
            settings = OBSData(settings)
        get_lib().obs_source_update(self._ptr, settings._ptr)

    # ------------------------------------------------------------------
    # Signal handler
    # ------------------------------------------------------------------

    def get_signal_handler(self):
        return get_lib().obs_source_get_signal_handler(self._ptr)

    # ------------------------------------------------------------------
    # Reference counting
    # ------------------------------------------------------------------

    def release(self) -> None:
        if self._ptr != ffi.NULL and self._owned and is_alive():
            lib = get_lib()
            # Mark the source as removed first — some plugin source types
            # (notably text_gdiplus_v3) need this signal to properly clean up
            # their GPU resources before obs_shutdown tears down the gfx ctx.
            try:
                lib.obs_source_remove(self._ptr)
            except Exception:
                pass
            lib.obs_source_release(self._ptr)
        self._ptr = ffi.NULL

    def __del__(self) -> None:
        try:
            self.release()
        except Exception:
            pass

    def __repr__(self) -> str:
        try:
            return f"Source(id={self.id!r}, name={self.name!r}, owned={self._owned})"
        except Exception:
            return f"Source(ptr={self._ptr})"
