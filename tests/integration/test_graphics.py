"""Integration tests for offscreen source readback (render_source_to_bgra)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def _center_bgra(data: bytes, stride: int, width: int, height: int) -> tuple:
    off = (height // 2) * stride + (width // 2) * 4
    return tuple(data[off : off + 4])


def test_render_source_to_bgra_reads_a_specific_scene_independent_of_program():
    """A specific scene reads back as its own pixels, not the program main mix."""
    from pylibobs import OBSContext, Scene, Source, render_source_to_bgra
    from pylibobs._ffi import get_lib

    with OBSContext() as obs:
        obs.set_video(320, 180, fps_num=30)
        obs.set_audio()
        obs.load_modules()

        # Program (main mix) = red, on output channel 0.
        program = Scene.create("prog")
        get_lib().obs_set_output_source(0, program.as_source()._ptr)
        red = Source.create(
            "color_source_v3", "red",
            {"color": 0xFF0000FF, "width": 320, "height": 180},  # 0xAABBGGRR → red
        )
        program.add(red)

        # Preview scene = green, never placed on any output channel.
        preview = Scene.create("prev")
        green = Source.create(
            "color_source_v3", "green",
            {"color": 0xFF00FF00, "width": 320, "height": 180},  # green
        )
        preview.add(green)

        result = render_source_to_bgra(
            preview.as_source(), 160, 90, canvas_width=320, canvas_height=180
        )
        assert result is not None
        data, stride = result
        assert stride >= 160 * 4
        assert len(data) == stride * 90

        b, g, r, _a = _center_bgra(data, stride, 160, 90)
        assert g > 150 and r < 80 and b < 80, (b, g, r)  # green, not the red program


def test_render_source_to_bgra_null_source_returns_none():
    from pylibobs import OBSContext, render_source_to_bgra

    with OBSContext() as obs:
        obs.set_video(320, 180, fps_num=30)
        obs.set_audio()
        obs.load_modules()
        assert render_source_to_bgra(None, 160, 90) is None
