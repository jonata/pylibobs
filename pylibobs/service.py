"""
Service — wrapper for obs_service_t.

Usage::

    svc = Service.create("rtmp_common", "twitch",
                         {"server": "rtmp://live.twitch.tv/app", "key": "live_xxx"})
"""

from __future__ import annotations

from ._ffi import ffi, get_lib, is_alive, register_wrapper
from .data import OBSData


class Service:
    """Wraps obs_service_t."""

    __slots__ = ("_ptr", "_owned", "__weakref__")

    def __init__(self, ptr, *, owned: bool = True) -> None:
        if ptr == ffi.NULL:
            raise ValueError("Cannot wrap NULL obs_service_t pointer")
        self._ptr = ptr
        self._owned = owned
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
    ) -> "Service":
        lib = get_lib()
        if isinstance(settings, dict):
            settings = OBSData(settings)
        s_ptr = settings._ptr if settings else ffi.NULL
        ptr = lib.obs_service_create(kind.encode(), name.encode(), s_ptr, ffi.NULL)
        if ptr == ffi.NULL:
            raise RuntimeError(
                f"obs_service_create returned NULL for kind={kind!r}. "
                "Is the service plugin loaded?"
            )
        return cls(ptr)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def id(self) -> str:
        raw = get_lib().obs_service_get_id(self._ptr)
        return ffi.string(raw).decode() if raw != ffi.NULL else ""

    @property
    def name(self) -> str:
        raw = get_lib().obs_service_get_name(self._ptr)
        return ffi.string(raw).decode() if raw != ffi.NULL else ""

    # OBS 32 removed obs_service_get_url/key/username/password as direct
    # accessors. Read them from the service's settings dict — the keys are
    # the standard "server" / "key" / "username" / "password".

    @property
    def url(self) -> str:
        return self.get_settings().get_string("server")

    @property
    def key(self) -> str:
        return self.get_settings().get_string("key")

    @property
    def username(self) -> str:
        return self.get_settings().get_string("username")

    @property
    def password(self) -> str:
        return self.get_settings().get_string("password")

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def get_settings(self) -> OBSData:
        ptr = get_lib().obs_service_get_settings(self._ptr)
        return OBSData(_ptr=ptr, _owned=True)

    def update(self, settings: OBSData | dict) -> None:
        if isinstance(settings, dict):
            settings = OBSData(settings)
        get_lib().obs_service_update(self._ptr, settings._ptr)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def release(self) -> None:
        if self._ptr != ffi.NULL and self._owned and is_alive():
            get_lib().obs_service_release(self._ptr)
        self._ptr = ffi.NULL

    def __del__(self) -> None:
        try:
            self.release()
        except Exception:
            pass

    def __repr__(self) -> str:
        return f"Service(id={self.id!r}, name={self.name!r})"
