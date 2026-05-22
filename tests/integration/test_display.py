"""
Integration test for the Display wrapper (live preview API).

Creates a hidden top-level window via ctypes, attaches an obs_display_t to its
HWND, registers a draw callback, runs the libobs message loop briefly to let
frames render, then tears down. Verifies:

  * obs_display_create returns non-NULL
  * Draw callback fires (we count invocations)
  * Display resize works
  * Clean shutdown via the wrapper registry — no segfault at process exit
"""

from __future__ import annotations

import platform
import time

import pytest

pytestmark = pytest.mark.integration

pytest.importorskip("ctypes")
if platform.system() != "Windows":
    pytest.skip("Display.from_window requires Windows", allow_module_level=True)


def _make_hidden_hwnd():
    """Create a small invisible top-level window and return its HWND.

    We use a static common control class ("STATIC") so we don't have to
    register our own. The window is created with WS_POPUP (no chrome) and
    is never shown.
    """
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    CreateWindowExW = user32.CreateWindowExW
    CreateWindowExW.argtypes = [
        wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
        wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
    ]
    CreateWindowExW.restype = wintypes.HWND

    WS_POPUP = 0x80000000
    hwnd = CreateWindowExW(0, "STATIC", "pylibobs-test",
                            WS_POPUP, 0, 0, 640, 360,
                            None, None, None, None)
    if not hwnd:
        raise RuntimeError("CreateWindowExW failed")
    return hwnd, user32


def test_display_create_and_draw_callback_fires():
    from pylibobs import (
        OBSContext, Display, Scene, Source,
        render_main_texture_letterboxed,
    )
    from pylibobs._ffi import get_lib

    hwnd, user32 = _make_hidden_hwnd()
    try:
        with OBSContext() as obs:
            obs.set_video(640, 360, fps_num=30)
            obs.set_audio()
            obs.load_modules()

            scene = Scene.create("disp_test")
            get_lib().obs_set_output_source(0, scene.as_source()._ptr)
            src = Source.create("color_source_v3", "blue",
                              {"color": 0xFFFF0000, "width": 640, "height": 360})
            scene.add(src)

            display = Display.from_window(hwnd, 640, 360)
            assert display._ptr is not None

            calls = {"n": 0, "max_cx": 0, "max_cy": 0}
            def draw(cx, cy):
                calls["n"] += 1
                calls["max_cx"] = max(calls["max_cx"], cx)
                calls["max_cy"] = max(calls["max_cy"], cy)
                render_main_texture_letterboxed(640, 360, cx, cy)

            display.add_draw_callback(draw)

            # Resize works without exception (the actual swapchain resize
            # is queued on the graphics thread and may take a frame or two).
            display.resize(800, 450)

            # Let libobs run a few frames. The render thread is independent
            # of Python, so we just sleep.
            time.sleep(0.5)

            assert calls["n"] > 0, "draw callback never fired"
            assert calls["max_cx"] > 0
            assert calls["max_cy"] > 0
            # After half a second of frames, the resize should have taken
            # effect — the callback should have seen the new size at least once.
            assert calls["max_cx"] >= 800 or calls["max_cy"] >= 450, (
                f"display.resize did not take effect: max size seen = "
                f"({calls['max_cx']}, {calls['max_cy']})"
            )

            display.enabled = False
            assert display.enabled is False
            display.enabled = True
    finally:
        user32.DestroyWindow(hwnd)
