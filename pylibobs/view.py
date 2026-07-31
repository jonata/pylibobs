"""
View — wraps obs_view_t, an independent channel set with its own video mix.

An ``obs_view`` is a second, independent set of output channels (0–5), each
holding a source, composited into its *own* ``video_t`` — separate from the
global ``obs_set_output_source()`` channels that feed the main preview/program.
This lets you drive two independent compositions at once: e.g. a projector
showing media only, while a virtual camera sent to a call shows camera + media.

Usage::

    view = View.create()
    view.set_source(0, my_scene.as_source())   # channel 0 of this view
    video = view.add()                          # register mix; returns video_t*

    out = Output.create("virtualcam_output", "vcam")
    out.set_media(video, ctx.get_audio())       # bind the raw output to THIS mix
    out.start()
    ...
    out.stop(); out.release()
    view.remove(); view.release()               # remove() must precede destroy

A ``Display`` may render the view's composition with ``obs_view_render`` inside
its draw callback (``view.render()``), giving an independent live preview.
"""

from __future__ import annotations

from ._ffi import ffi, get_lib, is_alive, register_wrapper
from .source import Source


class View:
    """Wraps obs_view_t — an independent channel set / video mix."""

    __slots__ = ("_ptr", "_owned", "_added", "__weakref__")

    def __init__(self, ptr, *, owned: bool = True) -> None:
        if ptr == ffi.NULL:
            raise ValueError("Cannot wrap NULL obs_view_t pointer")
        self._ptr = ptr
        self._owned = owned
        self._added = False
        if owned:
            register_wrapper(self)

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def create(cls) -> "View":
        ptr = get_lib().obs_view_create()
        if ptr == ffi.NULL:
            raise RuntimeError("obs_view_create returned NULL")
        return cls(ptr)

    # ------------------------------------------------------------------
    # Channels
    # ------------------------------------------------------------------

    def set_source(self, channel: int, source: Source | None) -> None:
        """Set the source shown on ``channel`` (0–5) of this view.

        libobs takes its own reference; pass ``None`` to clear the channel.
        """
        get_lib().obs_view_set_source(
            self._ptr, int(channel),
            source._ptr if source is not None else ffi.NULL,
        )

    def get_source(self, channel: int) -> Source | None:
        """Return the source on ``channel``, or ``None``.

        obs_view_get_source returns a STRONG reference, so the returned Source
        owns it and will release it — do not use it after this view is gone.
        """
        ptr = get_lib().obs_view_get_source(self._ptr, int(channel))
        return Source(ptr, owned=True) if ptr != ffi.NULL else None

    # ------------------------------------------------------------------
    # Video mix
    # ------------------------------------------------------------------

    def add(self):
        """Register this view as a video mix in the render loop.

        Returns the view's own ``video_t*`` (a raw cffi pointer to bind a raw
        output to via :meth:`Output.set_media`), or ``None`` on failure.
        Must be paired with :meth:`remove` before :meth:`release`/destroy.
        """
        video = get_lib().obs_view_add(self._ptr)
        self._added = bool(video)
        return video if video != ffi.NULL else None

    def add2(self, ovi):
        """Like :meth:`add`, but composite at a custom resolution/format.

        ``ovi`` is a ``struct obs_video_info *`` (cffi). Returns the view's
        ``video_t*`` or ``None``.
        """
        video = get_lib().obs_view_add2(self._ptr, ovi)
        self._added = bool(video)
        return video if video != ffi.NULL else None

    def render(self) -> None:
        """Render this view's composition — call from a Display draw callback."""
        get_lib().obs_view_render(self._ptr)

    def remove(self) -> None:
        """Unregister the video mix. Must be called before destroy if added."""
        if self._added and self._ptr != ffi.NULL and is_alive():
            get_lib().obs_view_remove(self._ptr)
        self._added = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def release(self) -> None:
        if self._ptr != ffi.NULL and self._owned and is_alive():
            # A view that is still added as a mix must be removed before
            # obs_view_destroy, otherwise libobs asserts / leaves a dangling
            # mix in the render loop.
            self.remove()
            get_lib().obs_view_destroy(self._ptr)
        self._ptr = ffi.NULL
        self._added = False

    def __del__(self) -> None:
        try:
            self.release()
        except Exception:
            pass

    def __repr__(self) -> str:
        return f"View(ptr={self._ptr}, added={self._added})"
