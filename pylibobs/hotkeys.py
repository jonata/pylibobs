"""
Hotkey — frontend / source hotkey registration with Python callbacks.

libobs hotkeys are decoupled from the OS keyboard input. You register a
hotkey by *name* and get back an `obs_hotkey_id`. The actual key combination
that triggers it is bound separately (saved/loaded via `obs_hotkey_save` /
`obs_hotkey_load`). For programmatic triggering use `Hotkey.trigger()`.

Use::

    def on_record(pressed):
        if pressed:
            output.start()

    hk = Hotkey.register_frontend("start_recording",
                                  "Start Recording", on_record)
    hk.trigger(pressed=True)   # fire the callback as if the key was pressed
"""

from __future__ import annotations

from enum import IntEnum, IntFlag
from typing import Callable

from ._ffi import ffi, get_lib, is_alive, register_wrapper


# obs_interaction_flags — modifiers in obs_key_combination
class KeyModifier(IntFlag):
    NONE     = 0
    CAPS     = 1 << 0
    SHIFT    = 1 << 1
    CONTROL  = 1 << 2
    ALT      = 1 << 3
    COMMAND  = 1 << 4   # macOS
    NUMLOCK  = 1 << 5


_INVALID_ID = (1 << 64) - 1  # obs_hotkey_id is size_t, OBS_INVALID_HOTKEY_ID = -1


def _ensure_rerouting_enabled() -> None:
    """obs_hotkey_trigger_routed_callback only fires the callback when
    callback-rerouting is enabled. We call it every registration because
    libobs resets the flag across obs_startup/shutdown cycles."""
    try:
        get_lib().obs_hotkey_enable_callback_rerouting(True)
    except Exception:
        pass


def enable_callback_rerouting(enable: bool = True) -> None:
    """Opt out of OBS's hotkey rerouting (in case a host app wants to handle
    callbacks itself). On by default after the first Hotkey registration."""
    get_lib().obs_hotkey_enable_callback_rerouting(bool(enable))


def enable_background_press(enable: bool = True) -> None:
    """Enable hotkeys to fire when the host application is not focused."""
    get_lib().obs_hotkey_enable_background_press(bool(enable))


def key_from_name(name: str) -> int:
    """Convert a libobs key name (e.g. 'OBS_KEY_F1') to its int code."""
    return int(get_lib().obs_key_from_name(name.encode()))


def key_to_name(code: int) -> str:
    raw = get_lib().obs_key_to_name(int(code))
    return ffi.string(raw).decode() if raw != ffi.NULL else ""


def inject_key_event(key_name: str, modifiers: KeyModifier = KeyModifier.NONE,
                     pressed: bool = True) -> None:
    """Simulate a key event — any hotkey bound to this combination fires."""
    lib = get_lib()
    combo = ffi.new("struct obs_key_combination *")
    combo.key = key_from_name(key_name)
    combo.modifiers = int(modifiers)
    lib.obs_hotkey_inject_event(combo[0], bool(pressed))


class Hotkey:
    """Wraps a registered obs_hotkey_id with a Python callback."""

    __slots__ = ("_id", "_cb", "_name", "_description", "__weakref__")

    def __init__(self, hotkey_id: int, name: str, description: str, cb) -> None:
        self._id = hotkey_id
        self._cb = cb           # cffi callback — keep alive
        self._name = name
        self._description = description
        register_wrapper(self)

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------

    @classmethod
    def register_frontend(
        cls,
        name: str,
        description: str,
        callback: Callable[[bool], None],
    ) -> "Hotkey":
        """Register a frontend (app-wide) hotkey.

        `callback(pressed)` is called twice per key event: once with True on
        press, once with False on release. Wrap your logic accordingly.
        """
        lib = get_lib()

        @ffi.callback("void(void *, obs_hotkey_id, obs_hotkey_t *, bool)")
        def _trampoline(_data, _id, _hk, pressed):
            try:
                callback(bool(pressed))
            except Exception:
                pass

        _ensure_rerouting_enabled()
        hid = lib.obs_hotkey_register_frontend(
            name.encode(), description.encode(), _trampoline, ffi.NULL,
        )
        if int(hid) == _INVALID_ID:
            raise RuntimeError(f"obs_hotkey_register_frontend failed for {name!r}")
        return cls(int(hid), name, description, _trampoline)

    @classmethod
    def register_source(
        cls,
        source,
        name: str,
        description: str,
        callback: Callable[[bool], None],
    ) -> "Hotkey":
        """Register a per-source hotkey (saved alongside the source's settings)."""
        lib = get_lib()

        @ffi.callback("void(void *, obs_hotkey_id, obs_hotkey_t *, bool)")
        def _trampoline(_data, _id, _hk, pressed):
            try:
                callback(bool(pressed))
            except Exception:
                pass

        _ensure_rerouting_enabled()
        hid = lib.obs_hotkey_register_source(
            source._ptr, name.encode(), description.encode(),
            _trampoline, ffi.NULL,
        )
        if int(hid) == _INVALID_ID:
            raise RuntimeError(f"obs_hotkey_register_source failed for {name!r}")
        return cls(int(hid), name, description, _trampoline)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def id(self) -> int:
        return self._id

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------

    def trigger(self, pressed: bool = True) -> None:
        """Fire the hotkey's callback as if the bound key was pressed/released."""
        get_lib().obs_hotkey_trigger_routed_callback(self._id, bool(pressed))

    def release(self) -> None:
        """Unregister the hotkey from libobs."""
        if self._id != _INVALID_ID and is_alive():
            try:
                get_lib().obs_hotkey_unregister(self._id)
            except Exception:
                pass
        self._id = _INVALID_ID

    # Alias matching the rest of the package's release convention
    unregister = release

    def __del__(self) -> None:
        try: self.release()
        except Exception: pass

    def __repr__(self) -> str:
        return f"Hotkey(id={self._id}, name={self._name!r})"
