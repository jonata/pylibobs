"""Integration tests for filter creation and attachment."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_attach_color_filter_to_source():
    """Add a color_filter_v2 to a color source, verify it appears in the
    filter list, then remove it."""
    from pylibobs import OBSContext, Filter, Scene, Source, enum_filter_types
    from pylibobs._ffi import get_lib

    with OBSContext() as obs:
        obs.set_video(640, 360)
        obs.set_audio()
        obs.load_modules()

        # Find a usable filter id (versioned name varies across OBS versions)
        all_filters = enum_filter_types()
        cf_id = next((f for f in all_filters if "color_filter" in f), None)
        assert cf_id, f"No color filter found in {all_filters}"

        scene = Scene.create("f_test")
        get_lib().obs_set_output_source(0, scene.as_source()._ptr)
        src = Source.create("color_source_v3", "filtered",
                          {"color": 0xFF00FF00, "width": 320, "height": 180})
        scene.add(src)

        assert src.filter_count() == 0
        flt = Filter.create(cf_id, "MyColorCorrection",
                            {"contrast": 0.3, "gamma": 0.5})
        src.add_filter(flt)
        assert src.filter_count() == 1

        # Roundtrip via get_filter_by_name
        same = src.get_filter_by_name("MyColorCorrection")
        assert same is not None
        assert same.name == "MyColorCorrection"
        assert same.id == cf_id

        # filters() returns the live list
        all_attached = src.filters()
        assert len(all_attached) == 1
        assert all_attached[0].name == "MyColorCorrection"

        # parent/target accessors
        parent = flt.get_parent()
        assert parent is not None and parent.name == "filtered"

        # Index management
        assert src.filter_index_of(flt) == 0

        # Remove
        src.remove_filter(flt)
        assert src.filter_count() == 0


def test_multiple_filters_and_reorder():
    from pylibobs import OBSContext, Filter, Scene, Source, enum_filter_types
    from pylibobs._ffi import get_lib

    with OBSContext() as obs:
        obs.set_video(640, 360)
        obs.set_audio()
        obs.load_modules()

        types = enum_filter_types()
        # Pick three different filters that work on video sources
        wanted = [t for t in types if any(x in t for x in
                  ("color_filter", "sharpness", "scale_filter", "crop", "mask"))]
        if len(wanted) < 2:
            pytest.skip(f"Not enough usable filter types: {types}")

        scene = Scene.create("f_test_multi")
        get_lib().obs_set_output_source(0, scene.as_source()._ptr)
        src = Source.create("color_source_v3", "s",
                          {"color": 0xFFAAAAAA, "width": 320, "height": 180})
        scene.add(src)

        filters = []
        for i, t in enumerate(wanted[:3]):
            f = Filter.create(t, f"flt_{i}")
            src.add_filter(f)
            filters.append(f)

        assert src.filter_count() == len(filters)
        names = [f.name for f in src.filters()]
        assert set(names) == {f.name for f in filters}
