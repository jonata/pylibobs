"""Integration tests for media remux (lossless container conversion)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def _make_short_recording(path: Path, duration_sec: int = 2) -> Path:
    """Produce a tiny MKV recording so we have something to remux."""
    from pylibobs import (
        AudioEncoder, OBSContext, Output, Scene, Source, VideoEncoder,
    )
    from pylibobs._ffi import get_lib

    with OBSContext() as obs:
        obs.set_video(320, 180, fps_num=30)
        obs.set_audio()
        obs.load_modules()

        scene = Scene.create("remux_src")
        get_lib().obs_set_output_source(0, scene.as_source()._ptr)
        src = Source.create("color_source_v3", "c",
                          {"color": 0xFF008040, "width": 320, "height": 180})
        scene.add(src)

        venc = VideoEncoder.create("obs_x264", "v",
                                  {"rate_control": "CRF", "crf": 28,
                                   "preset": "veryfast"})
        aenc = AudioEncoder.create("ffmpeg_aac", "a", {"bitrate": 96})

        out = Output.create("ffmpeg_muxer", "rec", {"path": str(path)})
        out.set_video_encoder(venc)
        out.set_audio_encoder(aenc)
        assert out.start(), out.last_error
        time.sleep(duration_sec)
        out.stop(wait=True)

    return path


def test_remux_mkv_to_mp4(tmp_path: Path):
    from pylibobs.remux import MediaRemux

    in_path  = _make_short_recording(tmp_path / "src.mkv", duration_sec=2)
    assert in_path.exists() and in_path.stat().st_size > 1024

    out_path = tmp_path / "remuxed.mp4"
    progresses: list[float] = []

    with MediaRemux(in_path, out_path) as job:
        ok = job.run(progress=lambda pct: progresses.append(pct))

    assert ok is True
    assert out_path.exists()
    assert out_path.stat().st_size > 1024

    # Verify MP4 signature (ftyp box at the start)
    with open(out_path, "rb") as f:
        head = f.read(12)
    # MP4 file has 'ftyp' at offset 4
    assert b"ftyp" in head, f"Not a valid MP4 — head bytes: {head!r}"

    # Progress should have been called and ended near 1.0
    assert len(progresses) > 0
    assert max(progresses) >= 0.5  # Got at least halfway through


def test_remux_one_shot_helper(tmp_path: Path):
    """`remux(in, out)` is a one-line helper that wraps create+run+release."""
    from pylibobs.remux import remux

    in_path  = _make_short_recording(tmp_path / "h.mkv", duration_sec=1)
    out_path = tmp_path / "h.mp4"

    ok = remux(in_path, out_path)
    assert ok is True
    assert out_path.exists()


def test_can_remux_predicate(tmp_path: Path):
    """can_remux() returns True for valid pairs, False for nonsense."""
    from pylibobs.remux import MediaRemux

    valid_in = _make_short_recording(tmp_path / "v.mkv", duration_sec=1)
    assert MediaRemux.can_remux(valid_in, tmp_path / "v.mp4") is True

    # Non-existent input → False
    assert MediaRemux.can_remux(tmp_path / "nope.mkv", tmp_path / "x.mp4") is False
