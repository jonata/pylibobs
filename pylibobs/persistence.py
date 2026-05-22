"""
Save / load OBS sources and scene collections to JSON — same round-trip
shape OBS Studio uses for its `Scenes.json` files.

Use::

    # Save current scenes/sources to a file:
    save_all_sources_to_json("session.json")

    # Re-create them in a fresh OBSContext:
    load_all_sources_from_json("session.json")
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from ._ffi import ffi, get_lib
from .data import OBSData
from .source import Source


def save_source(source: Source) -> OBSData:
    """Serialise a single source to an obs_data_t containing its full state."""
    ptr = get_lib().obs_save_source(source._ptr)
    if ptr == ffi.NULL:
        raise RuntimeError("obs_save_source returned NULL")
    return OBSData(_ptr=ptr, _owned=True)


def load_source(data: OBSData) -> Source:
    """Re-create a source from data produced by `save_source`."""
    ptr = get_lib().obs_load_source(data._ptr)
    if ptr == ffi.NULL:
        raise RuntimeError("obs_load_source returned NULL — bad data?")
    return Source(ptr, owned=True)


def save_all_sources() -> "OBSDataArray":
    """Return an obs_data_array_t handle containing every live source.

    The handle has a small wrapper that supports indexing and conversion to
    a JSON string via `.to_json()`.
    """
    ptr = get_lib().obs_save_sources()
    if ptr == ffi.NULL:
        raise RuntimeError("obs_save_sources returned NULL")
    return OBSDataArray(ptr)


def load_all_sources(array: "OBSDataArray") -> None:
    """Re-create all sources from a data array previously returned by
    `save_all_sources()`. Sources are loaded into the global libobs runtime
    and become discoverable via `enum_sources()` / `enum_scenes()`."""
    lib = get_lib()

    @ffi.callback("void(void *, obs_source_t *)")
    def _cb(_pd, _src):
        pass  # we don't need to track each loaded source

    lib.obs_load_sources(array._ptr, _cb, ffi.NULL)


# ---------------------------------------------------------------------------
# JSON file round-trip
# ---------------------------------------------------------------------------
def save_all_sources_to_json(path: str | Path) -> None:
    """Save every live source to a JSON file, mimicking OBS Studio's
    Scenes.json format."""
    path = Path(path)
    arr = save_all_sources()
    try:
        path.write_text(arr.to_json(), encoding="utf-8")
    finally:
        arr.release()


def load_all_sources_from_json(path: str | Path) -> None:
    """Re-create every source from a JSON file previously saved via
    `save_all_sources_to_json`."""
    path = Path(path)
    arr = OBSDataArray.from_json(path.read_text(encoding="utf-8"))
    try:
        load_all_sources(arr)
    finally:
        arr.release()


# ---------------------------------------------------------------------------
# Thin obs_data_array_t wrapper (we declared the basics in _DATA already)
# ---------------------------------------------------------------------------
class OBSDataArray:
    """Wraps obs_data_array_t. Iterable over the underlying OBSData entries."""

    __slots__ = ("_ptr", "_owned")

    def __init__(self, ptr, *, owned: bool = True) -> None:
        if ptr == ffi.NULL:
            raise ValueError("Cannot wrap NULL obs_data_array_t pointer")
        self._ptr = ptr
        self._owned = owned

    @classmethod
    def create(cls) -> "OBSDataArray":
        return cls(get_lib().obs_data_array_create())

    @classmethod
    def from_json(cls, json_str: str) -> "OBSDataArray":
        """Reconstruct an array from a JSON list-of-objects string."""
        # libobs only parses *objects* from JSON. Wrap the array in an object
        # and pull it back out.
        wrapped = '{"arr":' + json_str + '}'
        data_ptr = get_lib().obs_data_create_from_json(wrapped.encode())
        if data_ptr == ffi.NULL:
            raise ValueError("Could not parse JSON")
        try:
            arr_ptr = get_lib().obs_data_get_array(data_ptr, b"arr")
            if arr_ptr == ffi.NULL:
                raise ValueError("JSON did not contain an 'arr' key")
            return cls(arr_ptr)
        finally:
            get_lib().obs_data_release(data_ptr)

    # ----- Container interface -----
    def __len__(self) -> int:
        return int(get_lib().obs_data_array_count(self._ptr))

    def __getitem__(self, idx: int) -> OBSData:
        if idx < 0 or idx >= len(self):
            raise IndexError(idx)
        ptr = get_lib().obs_data_array_item(self._ptr, int(idx))
        return OBSData(_ptr=ptr, _owned=True)

    def append(self, item: OBSData) -> int:
        return int(get_lib().obs_data_array_push_back(self._ptr, item._ptr))

    def insert(self, idx: int, item: OBSData) -> None:
        get_lib().obs_data_array_insert(self._ptr, int(idx), item._ptr)

    def erase(self, idx: int) -> None:
        get_lib().obs_data_array_erase(self._ptr, int(idx))

    def to_json(self) -> str:
        """Serialise to a JSON list-of-objects string."""
        # Wrap so libobs's JSON serialiser (object-only) can emit us.
        d = OBSData()
        get_lib().obs_data_set_array(d._ptr, b"arr", self._ptr)
        full = d.to_json()
        # full looks like: {"arr": [ ... ]} — extract the array text
        # Simple parse: find the '[' through matching ']'
        start = full.find("[")
        end   = full.rfind("]")
        if start == -1 or end == -1:
            return "[]"
        return full[start:end+1]

    # ----- Lifecycle -----
    def release(self) -> None:
        if self._ptr != ffi.NULL and self._owned:
            try:
                get_lib().obs_data_array_release(self._ptr)
            except Exception:
                pass
            self._ptr = ffi.NULL

    def __del__(self) -> None:
        try: self.release()
        except Exception: pass
