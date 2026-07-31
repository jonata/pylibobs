"""
Integration tests for the View wrapper (obs_view — independent video mix).

An obs_view is a second, independent set of channels composited into its own
video_t, separate from the global obs_set_output_source() channels. These tests
prove the view is genuinely independent: with the main mix (channel 0) showing
RED and the view showing GREEN, an output bound to the view's video_t records
GREEN — via both the encoder path (obs_encoder_set_video) and the raw-output
path (obs_output_set_media, the virtual-camera vehicle).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time

import pytest

pytestmark = pytest.mark.integration

RED = 0xFF0000FF    # libobs color is 0xAABBGGRR -> pure red
GREEN = 0xFF00FF00  # -> pure green


def _dominant_rgb(mp4_path: str):
    """Decode one frame with ffmpeg and return its average (R, G, B), or None
    if ffmpeg is unavailable / decoding fails."""
    if not shutil.which("ffmpeg"):
        return None
    raw = mp4_path + ".rgb"
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", mp4_path,
             "-vf", "select=eq(n\\,15)", "-vframes", "1",
             "-pix_fmt", "rgb24", "-f", "rawvideo", raw],
            check=True, capture_output=True,
        )
        data = open(raw, "rb").read()
    except (subprocess.CalledProcessError, OSError):
        return None
    finally:
        if os.path.exists(raw):
            os.remove(raw)
    n = len(data) // 3
    if n == 0:
        return None
    return (sum(data[0::3]) / n, sum(data[1::3]) / n, sum(data[2::3]) / n)


def test_view_is_independent_mix(tmp_path):
    """View.add() yields a distinct video_t; get_source roundtrips; teardown clean."""
    from pylibobs import OBSContext, Source, View
    from pylibobs._ffi import get_lib

    with OBSContext() as ctx:
        ctx.set_video(320, 180, fps_num=30)
        ctx.set_audio()
        ctx.load_modules()

        # Main mix (channel 0) = RED
        red = Source.create("color_source_v3", "red",
                            {"color": RED, "width": 320, "height": 180})
        get_lib().obs_set_output_source(0, red._ptr)

        view = View.create()
        green = Source.create("color_source_v3", "green",
                              {"color": GREEN, "width": 320, "height": 180})
        view.set_source(0, green)

        # get_source returns a strong ref to the same source
        got = view.get_source(0)
        assert got is not None and got.name == "green"
        got.release()

        video = view.add()
        assert video is not None
        # The view's mix is a *distinct* handle from the main mix
        assert video != ctx.get_video()
        assert ctx.get_audio() is not None

        view.remove()
        view.release()
    # Reaching here (context __exit__ -> shutdown) without a segfault is part
    # of the assertion.


def test_output_records_view_via_encoder(tmp_path):
    """An encoder bound to the view's mix records the view (GREEN), not main (RED)."""
    from pylibobs import (OBSContext, Source, View, Output,
                          VideoEncoder, AudioEncoder)
    from pylibobs._ffi import get_lib

    out_path = str(tmp_path / "view_enc.mp4")
    with OBSContext() as ctx:
        ctx.set_video(320, 180, fps_num=30)
        ctx.set_audio()
        ctx.load_modules()

        red = Source.create("color_source_v3", "red",
                            {"color": RED, "width": 320, "height": 180})
        get_lib().obs_set_output_source(0, red._ptr)

        view = View.create()
        green = Source.create("color_source_v3", "green",
                              {"color": GREEN, "width": 320, "height": 180})
        view.set_source(0, green)
        video = view.add()
        assert video is not None

        venc = VideoEncoder.create("obs_x264", "v",
                                   {"rate_control": "CRF", "crf": 20,
                                    "preset": "ultrafast"})
        venc.attach_video(video)                       # bind encoder to the VIEW
        aenc = AudioEncoder.create("ffmpeg_aac", "a", {"bitrate": 128})
        out = Output.create("mp4_output", "rec", {"path": out_path})
        out.set_video_encoder(venc)
        out.set_audio_encoder(aenc)

        assert out.start(), f"output.start() failed: {out.last_error}"
        time.sleep(1.2)
        assert out.total_frames > 0
        out.stop(wait=True)

        view.remove()
        view.release()

    assert os.path.getsize(out_path) > 0
    rgb = _dominant_rgb(out_path)
    if rgb is not None:
        r, g, b = rgb
        assert g > 150 and r < 80, f"expected GREEN view mix, got RGB={rgb}"


def test_set_media_binds_raw_output_to_view(tmp_path):
    """Output.set_media binds a RAW output to the view's video_t (the vcam path)."""
    from pylibobs import OBSContext, Source, View, Output
    from pylibobs._ffi import get_lib

    out_path = str(tmp_path / "view_raw.mp4")
    with OBSContext() as ctx:
        ctx.set_video(320, 180, fps_num=30)
        ctx.set_audio()
        ctx.load_modules()

        red = Source.create("color_source_v3", "red",
                            {"color": RED, "width": 320, "height": 180})
        get_lib().obs_set_output_source(0, red._ptr)

        view = View.create()
        green = Source.create("color_source_v3", "green",
                              {"color": GREEN, "width": 320, "height": 180})
        view.set_source(0, green)
        video = view.add()
        assert video is not None

        # ffmpeg_output is a RAW output — it encodes internally and takes its
        # frames from the video_t set via obs_output_set_media.
        out = Output.create("ffmpeg_output", "rawrec", {
            "url": out_path, "format_name": "mp4",
            "video_encoder": "libx264", "video_bitrate": 1000,
            "audio_encoder": "aac", "audio_bitrate": 128,
        })
        out.set_media(video, ctx.get_audio())          # RAW path -> VIEW mix

        assert out.start(), f"output.start() failed: {out.last_error}"
        time.sleep(1.2)
        assert out.total_frames > 0
        out.stop(wait=True)

        view.remove()
        view.release()

    assert os.path.getsize(out_path) > 0
    rgb = _dominant_rgb(out_path)
    if rgb is not None:
        r, g, b = rgb
        assert g > 150 and r < 80, f"expected GREEN view mix, got RGB={rgb}"
