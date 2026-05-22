"""
Integration test that exercises the same code paths as examples/pylibobs_studio.py
but without the GUI mainloop, so it can run in CI / on the command line.

Workflow:
  1. Initialize OBSContext
  2. Add multiple source types to the scene (color sources + monitor capture)
  3. Position and scale them
  4. Reorder
  5. Toggle visibility
  6. Record briefly to a file
  7. Verify the output exists and has bytes

If this passes, the GUI harness will work too — only the Tk plumbing differs.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def test_full_composition_workflow(tmp_path: Path) -> None:
    from pylibobs import (
        AudioEncoder,
        OBSContext,
        Output,
        Scene,
        Source,
        VideoEncoder,
    )
    from pylibobs._ffi import get_lib

    out_path = tmp_path / "workflow.mkv"

    with OBSContext(locale="en-US") as obs:
        obs.set_video(width=640, height=360, fps_num=30)
        obs.set_audio()
        obs.load_modules()

        scene = Scene.create("workflow_scene")
        get_lib().obs_set_output_source(0, scene.as_source()._ptr)

        # 1. Add several color sources at different positions
        sources_added: list[tuple[Source, object]] = []
        for i, (color, pos) in enumerate([
            (0xFF0000FF, (0,   0)),    # red top-left
            (0xFF00FF00, (320, 0)),    # green top-right
            (0xFFFF0000, (0,   180)),  # blue bottom-left
        ]):
            src = Source.create(
                "color_source_v3", f"color_{i}",
                {"color": color, "width": 320, "height": 180},
            )
            item = scene.add(src)
            item.pos = pos
            sources_added.append((src, item))

        assert len(scene.items()) == 3

        # 2. Add a monitor capture, scaled small
        try:
            cap = Source.create("monitor_capture", "Desktop", {"monitor": 0})
            cap_item = scene.add(cap)
            cap_item.pos = (320, 180)
            cap_item.scale = (0.5, 0.5)
        except RuntimeError:
            pass  # No monitor available in headless CI -- skip

        # 3. Verify position/scale roundtrip
        first_item = sources_added[1][1]
        first_item.pos = (123.0, 45.0)
        assert first_item.pos == (123.0, 45.0)
        first_item.scale = (1.5, 0.75)
        assert first_item.scale == (1.5, 0.75)

        # 4. Reorder: move first item to the back
        first_item.order_position = 0
        assert first_item.order_position == 0

        # 5. Toggle visibility
        first_item.visible = False
        assert first_item.visible is False
        first_item.visible = True
        assert first_item.visible is True

        # 6. Record briefly
        venc = VideoEncoder.create(
            "obs_x264", "workflow_v",
            {"rate_control": "CRF", "crf": 28, "preset": "veryfast"},
        )
        aenc = AudioEncoder.create("ffmpeg_aac", "workflow_a", {"bitrate": 96})

        output = Output.create("ffmpeg_muxer", "workflow_rec", {"path": str(out_path)})
        output.set_video_encoder(venc)
        output.set_audio_encoder(aenc)

        assert output.start(), f"output.start() failed: {output.last_error}"
        time.sleep(2.0)
        assert output.active
        output.stop(wait=True)

    # 7. Verify file was written
    assert out_path.exists(), f"Expected {out_path} to exist"
    size = out_path.stat().st_size
    assert size > 1024, f"Output file too small ({size} bytes); recording probably failed"

    # Verify MKV magic bytes
    with open(out_path, "rb") as f:
        magic = f.read(4)
    assert magic == b"\x1a\x45\xdf\xa3", f"Bad MKV magic: {magic.hex()}"
