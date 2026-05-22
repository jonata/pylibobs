"""
Display — wraps obs_display_t for live preview rendering into a native window.

Usage::

    # `hwnd` is the native window handle of a QWidget (use widget.winId())
    display = Display.from_window(hwnd, width=1280, height=720)
    display.add_draw_callback(my_draw_fn)

The draw callback is invoked by libobs on the graphics thread every frame.
A typical callback just calls `obs_render_main_texture()`, optionally inside
a viewport that letterboxes the canvas into the widget's actual size.
"""

from __future__ import annotations

import platform
from typing import Callable

from ._ffi import ffi, get_lib, is_alive, register_wrapper


# Sensible Windows defaults. On Linux/macOS the gs_window layout differs and
# isn't supported by this wrapper yet.
_DEFAULT_FORMAT_BGRA = 5     # GS_BGRA
_ZS_NONE = 0                 # GS_ZS_NONE
_DEFAULT_BG = 0xFF1A1A1A     # near-black


def render_main_texture_letterboxed(canvas_w: int, canvas_h: int,
                                    widget_w: int, widget_h: int) -> None:
    """
    Render the main OBS canvas into the current widget viewport with
    letterboxing so the aspect ratio is preserved.

    Call this inside a Display draw callback. It clears nothing; the
    display's background_color (set at create time) fills the bars.
    """
    if canvas_w <= 0 or canvas_h <= 0 or widget_w <= 0 or widget_h <= 0:
        return

    # Compute fit
    src_aspect = canvas_w / canvas_h
    dst_aspect = widget_w / widget_h
    if dst_aspect > src_aspect:
        # widget is wider than canvas — pillarbox
        scale = widget_h / canvas_h
        out_w = int(canvas_w * scale)
        out_h = widget_h
        x = (widget_w - out_w) // 2
        y = 0
    else:
        # widget is taller — letterbox
        scale = widget_w / canvas_w
        out_w = widget_w
        out_h = int(canvas_h * scale)
        x = 0
        y = (widget_h - out_h) // 2

    lib = get_lib()
    lib.gs_projection_push()
    lib.gs_set_viewport(x, y, out_w, out_h)
    lib.gs_ortho(0.0, float(canvas_w), 0.0, float(canvas_h), -100.0, 100.0)
    lib.obs_render_main_texture()
    lib.gs_projection_pop()


class Display:
    """Wraps obs_display_t. Hosts a live preview inside a native window."""

    __slots__ = ("_ptr", "_owned", "_draw_cbs", "__weakref__")

    def __init__(self, ptr, *, owned: bool = True) -> None:
        if ptr == ffi.NULL:
            raise ValueError("Cannot wrap NULL obs_display_t pointer")
        self._ptr = ptr
        self._owned = owned
        # Keep cffi callback wrappers alive; libobs holds raw fn pointers to them.
        self._draw_cbs: list = []
        if owned:
            register_wrapper(self)

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_window(
        cls,
        hwnd: int,
        width: int,
        height: int,
        *,
        background_color: int = _DEFAULT_BG,
        num_backbuffers: int = 1,
        adapter: int = 0,
    ) -> "Display":
        """
        Create an obs_display_t targeting a native window.

        Parameters
        ----------
        hwnd:    Native window handle (HWND on Windows).
        width:   Initial display width in pixels.
        height:  Initial display height in pixels.
        background_color: 0xAARRGGBB color used outside the rendered area.
        """
        if platform.system() != "Windows":
            raise NotImplementedError(
                "Display.from_window currently only supports Windows. "
                "Linux/macOS would need a different gs_window layout."
            )
        if not hwnd:
            raise ValueError("hwnd is 0/NULL")

        lib = get_lib()
        init = ffi.new("struct gs_init_data *")
        init.window.hwnd = ffi.cast("void *", int(hwnd))
        init.cx = int(width)
        init.cy = int(height)
        init.num_backbuffers = num_backbuffers
        init.format = _DEFAULT_FORMAT_BGRA
        init.zsformat = _ZS_NONE
        init.adapter = adapter

        ptr = lib.obs_display_create(init, background_color)
        if ptr == ffi.NULL:
            raise RuntimeError(
                "obs_display_create returned NULL. Check that obs_reset_video "
                "succeeded and that the window handle is valid."
            )
        return cls(ptr)

    # ------------------------------------------------------------------
    # Draw callbacks
    # ------------------------------------------------------------------

    def add_draw_callback(self, fn: Callable[[int, int], None]) -> None:
        """Register a Python callable to run on every preview frame.

        `fn` receives (display_cx, display_cy) — the current widget size.
        Inside `fn` you may call libobs draw functions, typically
        `pylibobs.display.render_main_texture_letterboxed(...)`.
        """
        lib = get_lib()

        @ffi.callback("void(void *, uint32_t, uint32_t)")
        def trampoline(_param, cx, cy):
            try:
                fn(int(cx), int(cy))
            except Exception:
                pass  # swallow — we're on libobs's graphics thread

        self._draw_cbs.append(trampoline)
        lib.obs_display_add_draw_callback(self._ptr, trampoline, ffi.NULL)

    # ------------------------------------------------------------------
    # Display state
    # ------------------------------------------------------------------

    def resize(self, width: int, height: int) -> None:
        get_lib().obs_display_resize(self._ptr, int(width), int(height))

    def set_background_color(self, argb: int) -> None:
        get_lib().obs_display_set_background_color(self._ptr, argb)

    @property
    def size(self) -> tuple[int, int]:
        w = ffi.new("uint32_t *")
        h = ffi.new("uint32_t *")
        get_lib().obs_display_size(self._ptr, w, h)
        return int(w[0]), int(h[0])

    @property
    def enabled(self) -> bool:
        return bool(get_lib().obs_display_enabled(self._ptr))

    @enabled.setter
    def enabled(self, value: bool) -> None:
        get_lib().obs_display_set_enabled(self._ptr, bool(value))

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def release(self) -> None:
        if self._ptr != ffi.NULL and self._owned and is_alive():
            lib = get_lib()
            # Quiesce first so no draw callbacks fire while we (or libobs's
            # graphics thread) are mid-teardown. This is the safe order
            # OBS Studio itself uses for QtDisplay teardown.
            try:
                lib.obs_display_set_enabled(self._ptr, False)
            except Exception:
                pass
            for cb in self._draw_cbs:
                try:
                    lib.obs_display_remove_draw_callback(self._ptr, cb, ffi.NULL)
                except Exception:
                    pass
            # Give the graphics thread a tick to drop any in-flight render.
            import time
            time.sleep(0.05)
            lib.obs_display_destroy(self._ptr)
        # Keep callbacks alive across release — libobs may still hold the
        # function pointer briefly. They are GC'd with self.
        self._ptr = ffi.NULL

    def __del__(self) -> None:
        try:
            self.release()
        except Exception:
            pass
