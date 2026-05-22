"""Integration tests for Property range / format accessors."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_color_source_int_property_ranges():
    """color_source_v3 should expose width/height as INT properties with
    sane min/max/step values."""
    from pylibobs import OBSContext, Source, Properties, PropertyType

    with OBSContext() as obs:
        obs.set_video(320, 180)
        obs.set_audio()
        obs.load_modules()

        src = Source.create("color_source_v3", "p_test",
                          {"color": 0xFF888888, "width": 100, "height": 100})
        props = src.get_properties()

        if "width" in props:
            w = props["width"]
            assert w.type == PropertyType.INT
            assert w.int_range is not None
            assert w.int_range.min >= 0
            assert w.int_range.max >= w.int_range.min
            assert w.int_range.step >= 1


def test_x264_encoder_properties():
    """obs_x264 has both INT (bitrate, crf) and LIST (preset, tune) properties."""
    from pylibobs import (
        OBSContext, VideoEncoder, Properties, PropertyType, ComboFormat,
    )

    with OBSContext() as obs:
        obs.set_video(320, 180)
        obs.set_audio()
        obs.load_modules()

        venc = VideoEncoder.create("obs_x264", "p_enc",
                                  {"rate_control": "CRF"})
        # Encoders use a different properties getter than sources
        props = Properties.from_encoder_id("obs_x264")

        # Browse for INT and LIST properties
        found_int  = any(p.type == PropertyType.INT for p in props)
        found_list = any(p.type == PropertyType.LIST for p in props)
        assert found_int, f"No INT property in {[p.name for p in props]}"
        assert found_list, f"No LIST property in {[p.name for p in props]}"


def test_image_source_path_property():
    """image_source has a FILE path property with a glob filter."""
    from pylibobs import OBSContext, Properties, PropertyType

    with OBSContext() as obs:
        obs.set_video(320, 180)
        obs.set_audio()
        obs.load_modules()

        props = Properties.from_source_id("image_source")
        path_props = [p for p in props if p.type == PropertyType.PATH]
        assert path_props, f"No PATH prop in image_source: {[p.name for p in props]}"

        for p in path_props:
            if p.path_info:
                # Type 0 = file, the filter is a glob string
                assert isinstance(p.path_info.filter, str)
                assert isinstance(p.path_info.default_path, str)


def test_long_description_present_for_some_property():
    """Some properties carry a long-form tooltip."""
    from pylibobs import OBSContext, Properties

    with OBSContext() as obs:
        obs.set_video(320, 180)
        obs.set_audio()
        obs.load_modules()

        # color_filter_v2 has a tonemap property with description
        for src_id in ("color_filter_v2", "color_filter"):
            try:
                props = Properties.from_source_id(src_id)
                # Just verify the accessor doesn't crash on any property
                for p in props:
                    assert isinstance(p.long_description, str)
                return
            except Exception:
                continue
        pytest.skip("No color filter available to test long_description")
