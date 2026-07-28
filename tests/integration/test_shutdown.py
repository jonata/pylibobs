"""Integration tests for clean libobs teardown.

Regression coverage for a Linux shutdown segfault: releasing a scene does not
destroy it synchronously (libobs defers scene teardown to its video/graphics
thread). If a scene still held items when obs_shutdown() ran, the deferred
destroy (obs_sceneitem_release -> obs_source_release) raced obs_shutdown()
freeing the same sources on the main thread — a double-free that crashed the
process. release_all_wrappers() now empties every scene before releasing, so
these must all exit cleanly (a crash shows up as a non-zero test process exit).
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_shutdown_with_populated_scene():
    """A scene with a live source must shut down without crashing."""
    from pylibobs import OBSContext, Scene, Source
    from pylibobs._ffi import get_lib, ffi

    with OBSContext() as obs:
        obs.set_video(640, 360)
        obs.set_audio()
        obs.load_modules()

        scene = Scene.create("shutdown_scene")
        get_lib().obs_set_output_source(0, scene.as_source()._ptr)
        src = Source.create(
            "color_source_v3", "shutdown_src",
            {"color": 0xFF0000FF, "width": 320, "height": 180},
        )
        scene.add(src)  # item intentionally discarded — scene owns it
    # __exit__ -> shutdown(); reaching here without SIGSEGV is the assertion.


def test_shutdown_with_multiple_scenes_and_sources():
    """Several scenes, each with multiple sources, must tear down cleanly."""
    from pylibobs import OBSContext, Scene, Source

    with OBSContext() as obs:
        obs.set_video(640, 360)
        obs.set_audio()
        obs.load_modules()

        for s in range(3):
            scene = Scene.create(f"scene_{s}")
            for i in range(4):
                src = Source.create(
                    "color_source_v3", f"src_{s}_{i}",
                    {"color": 0xFF00FF00, "width": 64, "height": 64},
                )
                scene.add(src)
    # Clean exit == pass.


def test_repeated_startup_shutdown_cycles():
    """Repeated full lifecycles in one process must not crash or leak fatally."""
    from pylibobs import OBSContext, Scene, Source

    for _ in range(3):
        with OBSContext() as obs:
            obs.set_video(640, 360)
            obs.set_audio()
            obs.load_modules()
            scene = Scene.create("cycle_scene")
            src = Source.create(
                "color_source_v3", "cycle_src",
                {"color": 0xFFFF0000, "width": 100, "height": 100},
            )
            scene.add(src)
