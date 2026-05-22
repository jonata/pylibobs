"""
Filter — a Source subclass that represents an obs_source_t with a filter-type id.

In libobs, filters share the same struct as sources but have a different
output_flag. You attach a filter to a source with `obs_source_filter_add()`.

Common filter types::

    "color_filter_v2"            # color correction
    "chroma_key_filter_v2"       # green-screen
    "noise_suppress_filter_v2"   # audio noise suppression
    "noise_gate_filter"          # audio noise gate
    "gain_filter"                # audio gain
    "compressor_filter"          # audio compressor
    "expander_filter"            # audio expander
    "limiter_filter"             # audio brick-wall limiter
    "scale_filter"               # video scaling
    "crop_filter"                # video crop / pad
    "gpu_delay"                  # frame delay
    "mask_filter_v2"             # image mask / alpha
    "sharpness_filter_v2"
    "luma_key_filter_v2"
"""

from __future__ import annotations

from typing import Callable

from ._ffi import ffi, get_lib
from .data import OBSData
from .source import Source


class Filter(Source):
    """Source-typed wrapper representing an OBS filter."""

    @classmethod
    def create(
        cls,
        kind: str,
        name: str,
        settings: OBSData | dict | None = None,
    ) -> "Filter":
        """Create a filter source. Use parent.add_filter(filter) to attach it."""
        # Filters are created with the same obs_source_create call.
        base = Source.create(kind, name, settings)
        # Re-wrap as Filter (copy ptr, transfer ownership).
        f = cls.__new__(cls)
        f._ptr = base._ptr
        f._owned = base._owned
        # Prevent the base wrapper from releasing now that we own the ref.
        base._owned = False
        base._ptr = ffi.NULL
        # Register the Filter as a wrapper (we took the ref from base).
        from ._ffi import register_wrapper
        register_wrapper(f)
        return f

    def get_parent(self) -> Source | None:
        """Return the source this filter is attached to (borrowed ref)."""
        ptr = get_lib().obs_filter_get_parent(self._ptr)
        return Source.borrow(ptr) if ptr != ffi.NULL else None

    def get_target(self) -> Source | None:
        """Return the filter's target source in the filter chain (borrowed ref)."""
        ptr = get_lib().obs_filter_get_target(self._ptr)
        return Source.borrow(ptr) if ptr != ffi.NULL else None

    def __repr__(self) -> str:
        return f"Filter(id={self.id!r}, name={self.name!r})"


# ---------------------------------------------------------------------------
# Bound to Source class as instance methods. We can't define them inside
# source.py (would create a circular import), so monkey-patch them here.
# ---------------------------------------------------------------------------

def _add_filter(self: Source, flt: Filter) -> None:
    """Attach a filter to this source. The filter must already be created."""
    get_lib().obs_source_filter_add(self._ptr, flt._ptr)


def _remove_filter(self: Source, flt: Filter) -> None:
    """Detach a filter from this source. The filter wrapper remains usable."""
    get_lib().obs_source_filter_remove(self._ptr, flt._ptr)


def _filter_count(self: Source) -> int:
    return int(get_lib().obs_source_filter_count(self._ptr))


def _get_filter_by_name(self: Source, name: str) -> "Filter | None":
    ptr = get_lib().obs_source_get_filter_by_name(self._ptr, name.encode())
    if ptr == ffi.NULL:
        return None
    f = Filter.__new__(Filter)
    f._ptr = ptr
    f._owned = True   # obs_source_get_filter_by_name returns +ref
    from ._ffi import register_wrapper
    register_wrapper(f)
    return f


def _filter_index_of(self: Source, flt: Filter) -> int:
    return int(get_lib().obs_source_filter_get_index(self._ptr, flt._ptr))


def _filter_set_index(self: Source, flt: Filter, index: int) -> None:
    get_lib().obs_source_filter_set_index(self._ptr, flt._ptr, int(index))


def _enum_filters(self: Source) -> list[Filter]:
    """Return a snapshot of this source's filters in current order.

    The callback gives us a borrowed ref; we promote it to a strong ref
    via obs_source_get_ref() so our wrapper can safely release later.
    """
    lib = get_lib()
    collected: list[Filter] = []

    @ffi.callback("void(obs_source_t *, obs_source_t *, void *)")
    def _cb(_parent, child, _param):
        if child == ffi.NULL:
            return
        strong = lib.obs_source_get_ref(child)
        if strong == ffi.NULL:
            return  # source is being destroyed
        f = Filter.__new__(Filter)
        f._ptr = strong
        f._owned = True
        from ._ffi import register_wrapper
        register_wrapper(f)
        collected.append(f)

    lib.obs_source_enum_filters(self._ptr, _cb, ffi.NULL)
    return collected


# Attach to Source class
Source.add_filter         = _add_filter           # type: ignore[attr-defined]
Source.remove_filter      = _remove_filter        # type: ignore[attr-defined]
Source.filter_count       = _filter_count         # type: ignore[attr-defined]
Source.get_filter_by_name = _get_filter_by_name   # type: ignore[attr-defined]
Source.filter_index_of    = _filter_index_of      # type: ignore[attr-defined]
Source.filter_set_index   = _filter_set_index     # type: ignore[attr-defined]
Source.filters            = _enum_filters         # type: ignore[attr-defined]


# Enumeration of registered filter type ids
def enum_filter_types() -> list[str]:
    """Return all libobs-registered filter source type ids (e.g. 'color_filter_v2')."""
    lib = get_lib()
    out: list[str] = []
    idx = 0
    sid_holder = ffi.new("const char **")
    while lib.obs_enum_filter_types(idx, sid_holder):
        if sid_holder[0] != ffi.NULL:
            out.append(ffi.string(sid_holder[0]).decode())
        idx += 1
    return out
