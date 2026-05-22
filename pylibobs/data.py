"""
OBSData — a dict-like wrapper around obs_data_t.

Type inference rules for __setitem__:
  str   → obs_data_set_string
  int   → obs_data_set_int
  float → obs_data_set_double
  bool  → obs_data_set_bool  (must test before int — bool subclasses int)
  dict  → obs_data_set_obj   (recursive OBSData)
  OBSData → obs_data_set_obj
"""

from __future__ import annotations

from collections.abc import Iterator, MutableMapping
from typing import Any

from ._ffi import ffi, get_lib


class OBSData(MutableMapping):
    """
    Pythonic wrapper for obs_data_t.

    Can be constructed from a dict::

        d = OBSData({"server": "rtmp://live.twitch.tv/app", "key": "live_xxx"})

    Supports iteration, len, and JSON serialisation.
    """

    __slots__ = ("_ptr", "_owned")

    def __init__(
        self,
        initial: dict[str, Any] | None = None,
        *,
        _ptr=None,
        _owned: bool = True,
    ) -> None:
        lib = get_lib()
        if _ptr is not None:
            self._ptr = _ptr
            self._owned = _owned
        else:
            self._ptr = lib.obs_data_create()
            self._owned = True

        if initial:
            for k, v in initial.items():
                self[k] = v

    # ------------------------------------------------------------------
    # MutableMapping interface
    # ------------------------------------------------------------------

    def __setitem__(self, key: str, value: Any) -> None:
        lib = get_lib()
        k = key.encode()
        if isinstance(value, bool):
            lib.obs_data_set_bool(self._ptr, k, value)
        elif isinstance(value, int):
            lib.obs_data_set_int(self._ptr, k, value)
        elif isinstance(value, float):
            lib.obs_data_set_double(self._ptr, k, value)
        elif isinstance(value, str):
            lib.obs_data_set_string(self._ptr, k, value.encode())
        elif isinstance(value, (dict, OBSData)):
            child = value if isinstance(value, OBSData) else OBSData(value)
            lib.obs_data_set_obj(self._ptr, k, child._ptr)
        else:
            raise TypeError(f"Cannot store {type(value).__name__!r} in OBSData")

    def __getitem__(self, key: str) -> Any:
        # We try each typed getter and return the first non-empty result.
        # For a real implementation the caller should use the typed getters
        # directly; __getitem__ does string-only for simplicity.
        lib = get_lib()
        k = key.encode()
        raw = lib.obs_data_get_string(self._ptr, k)
        if raw != ffi.NULL:
            s = ffi.string(raw).decode()
            if s:
                return s
        # Fall back to returning the JSON representation for the key
        raise KeyError(key)

    def __delitem__(self, key: str) -> None:
        get_lib().obs_data_erase(self._ptr, key.encode())

    def __iter__(self) -> Iterator[str]:
        # libobs doesn't expose a keys iterator; serialise to JSON and parse.
        import json
        return iter(json.loads(self.to_json()).keys())

    def __len__(self) -> int:
        import json
        return len(json.loads(self.to_json()))

    # ------------------------------------------------------------------
    # Typed getters (preferred over __getitem__ for type safety)
    # ------------------------------------------------------------------

    def get_string(self, key: str, default: str = "") -> str:
        lib = get_lib()
        raw = lib.obs_data_get_string(self._ptr, key.encode())
        if raw == ffi.NULL:
            return default
        return ffi.string(raw).decode()

    def get_int(self, key: str, default: int = 0) -> int:
        return int(get_lib().obs_data_get_int(self._ptr, key.encode())) or default

    def get_double(self, key: str, default: float = 0.0) -> float:
        return float(get_lib().obs_data_get_double(self._ptr, key.encode())) or default

    def get_bool(self, key: str, default: bool = False) -> bool:
        return bool(get_lib().obs_data_get_bool(self._ptr, key.encode()))

    def get_obj(self, key: str) -> "OBSData | None":
        lib = get_lib()
        ptr = lib.obs_data_get_obj(self._ptr, key.encode())
        if ptr == ffi.NULL:
            return None
        return OBSData(_ptr=ptr, _owned=True)

    # ------------------------------------------------------------------
    # Defaults — separate layer from user values
    # ------------------------------------------------------------------

    def set_default_string(self, key: str, value: str) -> None:
        get_lib().obs_data_set_default_string(self._ptr, key.encode(), value.encode())

    def set_default_int(self, key: str, value: int) -> None:
        get_lib().obs_data_set_default_int(self._ptr, key.encode(), int(value))

    def set_default_double(self, key: str, value: float) -> None:
        get_lib().obs_data_set_default_double(self._ptr, key.encode(), float(value))

    def set_default_bool(self, key: str, value: bool) -> None:
        get_lib().obs_data_set_default_bool(self._ptr, key.encode(), bool(value))

    def get_default_string(self, key: str) -> str:
        raw = get_lib().obs_data_get_default_string(self._ptr, key.encode())
        return ffi.string(raw).decode() if raw != ffi.NULL else ""

    def get_default_int(self, key: str) -> int:
        return int(get_lib().obs_data_get_default_int(self._ptr, key.encode()))

    def get_default_double(self, key: str) -> float:
        return float(get_lib().obs_data_get_default_double(self._ptr, key.encode()))

    def get_default_bool(self, key: str) -> bool:
        return bool(get_lib().obs_data_get_default_bool(self._ptr, key.encode()))

    def has_default_value(self, key: str) -> bool:
        return bool(get_lib().obs_data_has_default_value(self._ptr, key.encode()))

    def has_user_value(self, key: str) -> bool:
        return bool(get_lib().obs_data_has_user_value(self._ptr, key.encode()))

    def unset_user_value(self, key: str) -> None:
        get_lib().obs_data_unset_user_value(self._ptr, key.encode())

    def unset_default_value(self, key: str) -> None:
        get_lib().obs_data_unset_default_value(self._ptr, key.encode())

    # ------------------------------------------------------------------
    # Iteration without round-tripping through JSON
    # ------------------------------------------------------------------

    def iter_items(self):
        """Yield (key, type_code) pairs walking the data directly via libobs."""
        lib = get_lib()
        holder = ffi.new("obs_data_item_t **")
        holder[0] = lib.obs_data_first(self._ptr)
        try:
            while holder[0] != ffi.NULL:
                name_ptr = lib.obs_data_item_get_name(holder[0])
                type_code = int(lib.obs_data_item_gettype(holder[0]))
                yield (ffi.string(name_ptr).decode() if name_ptr != ffi.NULL else ""), type_code
                if not lib.obs_data_item_next(holder):
                    break
        finally:
            if holder[0] != ffi.NULL:
                lib.obs_data_item_release(holder)

    # ------------------------------------------------------------------
    # Merge / save
    # ------------------------------------------------------------------

    def apply(self, other: "OBSData") -> None:
        """Merge keys from `other` into self, overwriting any matching keys."""
        get_lib().obs_data_apply(self._ptr, other._ptr)

    def save_json(self, path) -> bool:
        """Write to a JSON file. Returns True on success."""
        return bool(get_lib().obs_data_save_json(self._ptr, str(path).encode()))

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_json(self) -> str:
        lib = get_lib()
        raw = lib.obs_data_get_json(self._ptr)
        if raw == ffi.NULL:
            return "{}"
        return ffi.string(raw).decode()

    @classmethod
    def from_json(cls, json_str: str) -> "OBSData":
        lib = get_lib()
        ptr = lib.obs_data_create_from_json(json_str.encode())
        if ptr == ffi.NULL:
            raise ValueError("obs_data_create_from_json returned NULL — invalid JSON?")
        return cls(_ptr=ptr, _owned=True)

    @classmethod
    def from_json_file(cls, path: str) -> "OBSData":
        lib = get_lib()
        ptr = lib.obs_data_create_from_json_file(path.encode())
        if ptr == ffi.NULL:
            raise FileNotFoundError(f"obs_data_create_from_json_file could not read: {path!r}")
        return cls(_ptr=ptr, _owned=True)

    # ------------------------------------------------------------------
    # Reference counting / cleanup
    # ------------------------------------------------------------------

    def addref(self) -> None:
        get_lib().obs_data_addref(self._ptr)

    def release(self) -> None:
        if self._ptr != ffi.NULL and self._owned:
            try:
                get_lib().obs_data_release(self._ptr)
            except Exception:
                pass
            self._ptr = ffi.NULL

    def __del__(self) -> None:
        try:
            self.release()
        except Exception:
            pass

    def __repr__(self) -> str:
        return f"OBSData({self.to_json()})"
