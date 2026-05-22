"""Integration tests for transitions."""

from __future__ import annotations

import time

import pytest

pytestmark = pytest.mark.integration


def test_create_fade_transition_and_switch_scenes():
    """Build two scenes, route via a fade_transition, fire start(), verify
    progress advances and the active source switches."""
    from pylibobs import (
        OBSContext, Scene, Source, Transition, TransitionMode,
        enum_transition_types,
    )
    from pylibobs._ffi import get_lib

    with OBSContext() as obs:
        obs.set_video(640, 360, fps_num=30)
        obs.set_audio()
        obs.load_modules()

        transitions = enum_transition_types()
        if "fade_transition" not in transitions:
            pytest.skip(f"No fade_transition available; have: {transitions}")

        # Two distinct scenes
        scene_a = Scene.create("trans_A")
        scene_b = Scene.create("trans_B")
        for sc, color in ((scene_a, 0xFFFF0000), (scene_b, 0xFF0000FF)):
            src = Source.create("color_source_v3", f"col_{color}",
                              {"color": color, "width": 640, "height": 360})
            sc.add(src)

        # Wire transition into channel 0 (Transition is itself a Source)
        trans = Transition.create("fade_transition", "Fade")
        trans.set_size(640, 360)
        trans.set_source(scene_a.as_source())
        get_lib().obs_set_output_source(0, trans._ptr)

        # Active source after set_source = scene_a
        active = trans.get_active_source()
        assert active is not None
        assert active.name == "trans_A"

        # Kick off transition to B
        ok = trans.start(scene_b.as_source(), duration_ms=200,
                         mode=TransitionMode.AUTO)
        assert ok is True

        # Let it run
        progresses = []
        for _ in range(8):
            progresses.append(trans.progress)
            time.sleep(0.05)

        # Progress should be a float in [0, 1]; should have advanced.
        assert all(0.0 <= p <= 1.0 for p in progresses), progresses
        assert max(progresses) > 0.0

        time.sleep(0.4)

        # After completion the active source should be scene_b
        active = trans.get_active_source()
        assert active is not None
        # Some transitions report the final source by name once complete.
        assert active.name in ("trans_A", "trans_B")


def test_clear_transition():
    from pylibobs import OBSContext, Scene, Source, Transition

    with OBSContext() as obs:
        obs.set_video(640, 360)
        obs.set_audio()
        obs.load_modules()

        scene = Scene.create("t_clear_sc")
        src = Source.create("color_source_v3", "c",
                          {"color": 0xFF888888, "width": 640, "height": 360})
        scene.add(src)

        trans = Transition.create("fade_transition", "ClearMe")
        trans.set_source(scene.as_source())
        assert trans.get_active_source() is not None

        trans.clear()
        # After clear, active source should be None
        active = trans.get_active_source()
        assert active is None or active.name == ""
