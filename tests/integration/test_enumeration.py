"""Integration tests for enumeration / introspection APIs."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_source_type_enumeration():
    """libobs should expose at least the source types we know are bundled."""
    from pylibobs import OBSContext, enum_source_types, enum_input_types, enum_input_types2

    with OBSContext() as obs:
        obs.set_video(640, 360)
        obs.set_audio()
        obs.load_modules()

        all_types = enum_source_types()
        inputs    = enum_input_types()
        inputs2   = enum_input_types2()

        # Sanity: dozens of types should be registered after modules load
        assert len(all_types) > 20, f"Only {len(all_types)} source types registered"
        assert len(inputs) > 5

        # Specific source types we use elsewhere in the project
        for required in ["color_source_v3", "monitor_capture", "image_source"]:
            assert required in all_types, f"Expected {required} in {all_types[:10]}..."

        # enum_input_types2 returns versioned + unversioned ids
        unversioned = {it.unversioned_id for it in inputs2}
        assert "color_source" in unversioned


def test_filter_and_transition_type_enumeration():
    from pylibobs import OBSContext, enum_filter_types, enum_transition_types

    with OBSContext() as obs:
        obs.set_video(640, 360)
        obs.set_audio()
        obs.load_modules()

        filters = enum_filter_types()
        transitions = enum_transition_types()

        # OBS ships a bunch of filters and transitions; just sanity-check
        assert len(filters) > 5, f"Filters: {filters}"
        assert any("color" in f or "gain" in f or "noise" in f for f in filters)

        assert "fade_transition" in transitions or "cut_transition" in transitions, (
            f"Transitions: {transitions}"
        )


def test_encoder_output_service_type_enumeration():
    from pylibobs import (
        OBSContext,
        enum_encoder_types, enum_output_types, enum_service_types,
        get_encoder_display_name, get_output_display_name,
    )

    with OBSContext() as obs:
        obs.set_video(640, 360)
        obs.set_audio()
        obs.load_modules()

        enc = enum_encoder_types()
        out = enum_output_types()
        svc = enum_service_types()

        assert "obs_x264" in enc
        assert "ffmpeg_aac" in enc
        assert "ffmpeg_muxer" in out
        # rtmp_common is the standard streaming service plugin
        assert any("rtmp" in s for s in svc), f"Services: {svc}"

        # display names are human-readable
        assert get_encoder_display_name("obs_x264")  # non-empty
        assert get_output_display_name("ffmpeg_muxer")


def test_get_source_defaults_for_color_source():
    """Defaults dict for color_source_v3 should include width/height."""
    from pylibobs import OBSContext, get_source_defaults

    with OBSContext() as obs:
        obs.set_video(640, 360)
        obs.set_audio()
        obs.load_modules()

        d = get_source_defaults("color_source_v3")
        assert d is not None
        # Default color_source has positive width and height
        assert d.get_int("width") > 0
        assert d.get_int("height") > 0


def test_live_enumeration_sources_and_scenes():
    """After creating sources/scenes, enum_* should find them."""
    from pylibobs import (
        OBSContext, Scene, Source,
        enum_sources, enum_scenes, enum_all_sources,
    )
    from pylibobs._ffi import get_lib

    with OBSContext() as obs:
        obs.set_video(640, 360)
        obs.set_audio()
        obs.load_modules()

        scene_a = Scene.create("enum_scene_a")
        scene_b = Scene.create("enum_scene_b")
        get_lib().obs_set_output_source(0, scene_a.as_source()._ptr)

        src1 = Source.create("color_source_v3", "enum_src_red",
                           {"color": 0xFF0000FF, "width": 64, "height": 64})
        src2 = Source.create("color_source_v3", "enum_src_blue",
                           {"color": 0xFFFF0000, "width": 64, "height": 64})
        scene_a.add(src1)
        scene_a.add(src2)

        scenes = enum_scenes()
        scene_names = {s.as_source().name for s in scenes}
        assert "enum_scene_a" in scene_names
        assert "enum_scene_b" in scene_names

        live_sources = enum_sources()
        src_names = {s.name for s in live_sources}
        # enum_sources returns inputs only, not the scene-source itself
        assert "enum_src_red" in src_names
        assert "enum_src_blue" in src_names

        # enum_all_sources includes everything
        all_names = {s.name for s in enum_all_sources()}
        assert "enum_scene_a" in all_names
        assert "enum_src_red" in all_names


def test_audio_monitoring_device_enumeration():
    """Should return at least the 'Default' device on any sane system."""
    from pylibobs import (
        OBSContext, audio_monitoring_available, enum_audio_monitoring_devices,
    )

    with OBSContext() as obs:
        obs.set_video(640, 360)
        obs.set_audio()
        obs.load_modules()

        # Just checking it doesn't crash and returns a list
        avail = audio_monitoring_available()
        assert isinstance(avail, bool)

        devices = enum_audio_monitoring_devices()
        assert isinstance(devices, list)
        # On real Windows we expect ≥ 1 device; in CI it may be 0
        for d in devices:
            assert d.name
            # On Windows id can be an empty string for the system-default —
            # just check the attribute is present.
            assert hasattr(d, "id")
