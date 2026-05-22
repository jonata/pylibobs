"""
Transition — a Source subclass representing an obs_source_t with a
transition-type id.

A transition holds an "A" source and lets you smoothly cross-fade to a
destination "B" source over a duration.

Common transition types::

    "cut_transition"             # instant cut (0 ms)
    "fade_transition"            # cross-fade
    "swipe_transition"           # swipe in from a direction
    "slide_transition"           # slide
    "fade_to_color_transition"   # fade through a solid color
    "luma_wipe_transition"       # luma-keyed wipe

Use::

    transition = Transition.create("fade_transition", "FadeT")
    # route to program output through the transition (instead of the scene)
    obs_set_output_source(0, transition.as_source()._ptr)
    transition.set_source(scene_a)
    ...
    transition.start(scene_b, duration_ms=600)
"""

from __future__ import annotations

from enum import IntEnum

from ._ffi import ffi, get_lib
from .data import OBSData
from .source import Source


class TransitionMode(IntEnum):
    AUTO   = 0
    MANUAL = 1


class Transition(Source):
    """Source-typed wrapper for an OBS transition."""

    @classmethod
    def create(
        cls,
        kind: str,
        name: str,
        settings: OBSData | dict | None = None,
    ) -> "Transition":
        base = Source.create(kind, name, settings)
        t = cls.__new__(cls)
        t._ptr = base._ptr
        t._owned = base._owned
        base._owned = False
        base._ptr = ffi.NULL
        from ._ffi import register_wrapper
        register_wrapper(t)
        return t

    # ------------------------------------------------------------------
    # Sources A/B
    # ------------------------------------------------------------------

    def set_source(self, source: Source) -> None:
        """Set the source the transition currently shows (the 'A' source)."""
        get_lib().obs_transition_set(self._ptr, source._ptr)

    def clear(self) -> None:
        """Detach the active source — transition becomes blank."""
        get_lib().obs_transition_clear(self._ptr)

    def get_active_source(self) -> Source | None:
        """Return the transition's currently-active source.

        obs_transition_get_active_source returns a STRONG reference (the
        caller must release), so we wrap it as owned.
        """
        ptr = get_lib().obs_transition_get_active_source(self._ptr)
        return Source(ptr, owned=True) if ptr != ffi.NULL else None

    # ------------------------------------------------------------------
    # Start
    # ------------------------------------------------------------------

    def start(
        self,
        destination: Source,
        duration_ms: int = 500,
        mode: TransitionMode = TransitionMode.AUTO,
    ) -> bool:
        """Begin transitioning to `destination`. Returns False if already running."""
        return bool(get_lib().obs_transition_start(
            self._ptr, int(mode), int(duration_ms), destination._ptr,
        ))

    # ------------------------------------------------------------------
    # Sizing — transitions need to know the canvas size for some effects
    # ------------------------------------------------------------------

    def set_size(self, cx: int, cy: int) -> None:
        get_lib().obs_transition_set_size(self._ptr, int(cx), int(cy))

    def get_size(self) -> tuple[int, int]:
        cx = ffi.new("uint32_t *")
        cy = ffi.new("uint32_t *")
        get_lib().obs_transition_get_size(self._ptr, cx, cy)
        return int(cx[0]), int(cy[0])

    @property
    def progress(self) -> float:
        """Current transition progress in [0.0, 1.0]."""
        return float(get_lib().obs_transition_get_time(self._ptr))

    def __repr__(self) -> str:
        return f"Transition(id={self.id!r}, name={self.name!r})"


def enum_transition_types() -> list[str]:
    """Return all libobs-registered transition source type ids."""
    lib = get_lib()
    out: list[str] = []
    idx = 0
    sid_holder = ffi.new("const char **")
    while lib.obs_enum_transition_types(idx, sid_holder):
        if sid_holder[0] != ffi.NULL:
            out.append(ffi.string(sid_holder[0]).decode())
        idx += 1
    return out
