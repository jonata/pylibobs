"""Integration tests for scene-item transforms (alignment, bounds, blending,
crop, groups, bulk get/set_info2)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_alignment_roundtrip():
    from pylibobs import OBSContext, Alignment, Scene, Source
    from pylibobs._ffi import get_lib

    with OBSContext() as obs:
        obs.set_video(640, 360)
        obs.set_audio()
        obs.load_modules()

        scene = Scene.create("tr_align")
        get_lib().obs_set_output_source(0, scene.as_source()._ptr)
        src = Source.create("color_source_v3", "x",
                          {"color": 0xFF008000, "width": 100, "height": 100})
        item = scene.add(src)

        item.alignment = Alignment.LEFT | Alignment.TOP
        assert item.alignment == int(Alignment.LEFT | Alignment.TOP)

        item.alignment = Alignment.CENTER
        assert item.alignment == 0

        item.alignment = Alignment.RIGHT | Alignment.BOTTOM
        assert item.alignment == int(Alignment.RIGHT | Alignment.BOTTOM)


def test_bounds_and_crop_and_blending():
    from pylibobs import (
        OBSContext, BlendingMode, BoundsType, Scene, Source,
    )
    from pylibobs._ffi import get_lib

    with OBSContext() as obs:
        obs.set_video(640, 360)
        obs.set_audio()
        obs.load_modules()

        scene = Scene.create("tr_bnds")
        get_lib().obs_set_output_source(0, scene.as_source()._ptr)
        src = Source.create("color_source_v3", "x2",
                          {"color": 0xFF800080, "width": 200, "height": 200})
        item = scene.add(src)

        # Bounds
        item.bounds_type = BoundsType.SCALE_INNER
        item.bounds = (320.0, 180.0)
        assert item.bounds_type == int(BoundsType.SCALE_INNER)
        assert item.bounds == (320.0, 180.0)

        item.bounds_type = BoundsType.NONE
        assert item.bounds_type == 0

        # Crop
        item.crop = (10, 20, 30, 40)
        assert item.crop == (10, 20, 30, 40)

        # Blending
        item.blending_mode = BlendingMode.ADDITIVE
        assert item.blending_mode == int(BlendingMode.ADDITIVE)

        item.blending_mode = BlendingMode.SCREEN
        assert item.blending_mode == int(BlendingMode.SCREEN)


def test_get_set_info2_bulk():
    from pylibobs import (
        OBSContext, Alignment, BoundsType, Scene, Source, TransformInfo,
    )
    from pylibobs._ffi import get_lib

    with OBSContext() as obs:
        obs.set_video(640, 360)
        obs.set_audio()
        obs.load_modules()

        scene = Scene.create("tr_info")
        get_lib().obs_set_output_source(0, scene.as_source()._ptr)
        src = Source.create("color_source_v3", "x3",
                          {"color": 0xFF112233, "width": 80, "height": 80})
        item = scene.add(src)

        new_info = TransformInfo(
            pos=(50.0, 60.0),
            rotation=15.0,
            scale=(1.5, 0.75),
            alignment=int(Alignment.LEFT | Alignment.TOP),
            bounds_type=int(BoundsType.SCALE_INNER),
            bounds=(200.0, 150.0),
            bounds_alignment=int(Alignment.CENTER),
            crop_to_bounds=False,
            bounds_crop=(0, 0, 0, 0),
        )
        item.set_transform(new_info)

        back = item.get_transform()
        assert back.pos == (50.0, 60.0)
        assert abs(back.rotation - 15.0) < 0.01
        assert back.scale == (1.5, 0.75)
        assert back.bounds_type == int(BoundsType.SCALE_INNER)


def test_defer_update():
    """Deferred updates batch many edits; the final values should be visible
    after defer_update_end + force_update_transform."""
    from pylibobs import OBSContext, Scene, Source
    from pylibobs._ffi import get_lib

    with OBSContext() as obs:
        obs.set_video(640, 360)
        obs.set_audio()
        obs.load_modules()

        scene = Scene.create("tr_defer")
        get_lib().obs_set_output_source(0, scene.as_source()._ptr)
        src = Source.create("color_source_v3", "x4",
                          {"color": 0xFFAABBCC, "width": 50, "height": 50})
        item = scene.add(src)

        # Begin/end pair shouldn't lose any setters
        item.defer_update_begin()
        item.pos = (100.0, 200.0)
        item.scale = (2.0, 2.0)
        item.defer_update_end()
        item.force_update_transform()

        # libobs uses floats — allow tiny tolerance
        px, py = item.pos
        sx, sy = item.scale
        assert abs(px - 100.0) < 0.5
        assert abs(py - 200.0) < 0.5
        assert abs(sx - 2.0) < 0.05
        assert abs(sy - 2.0) < 0.05


def test_add_group():
    """obs_scene_add_group creates an empty group item; is_group reports True."""
    from pylibobs import OBSContext, Scene
    from pylibobs._ffi import get_lib

    with OBSContext() as obs:
        obs.set_video(640, 360)
        obs.set_audio()
        obs.load_modules()

        scene = Scene.create("tr_group")
        get_lib().obs_set_output_source(0, scene.as_source()._ptr)

        grp = scene.add_group("MyGroup")
        assert grp.is_group is True


def test_scene_duplicate():
    """Scene.duplicate copies a scene with all its sources."""
    from pylibobs import OBSContext, Scene, Source
    from pylibobs._ffi import get_lib

    with OBSContext() as obs:
        obs.set_video(640, 360)
        obs.set_audio()
        obs.load_modules()

        scene = Scene.create("dup_src")
        get_lib().obs_set_output_source(0, scene.as_source()._ptr)
        src = Source.create("color_source_v3", "in_orig",
                          {"color": 0xFFFFFFFF, "width": 50, "height": 50})
        scene.add(src)

        clone = scene.duplicate("dup_clone")
        assert len(clone.items()) >= 1
