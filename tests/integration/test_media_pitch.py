"""
Integration test for pitch-preserving Media Source speed.

The bundled obs-ffmpeg plugin is rebuilt from patched OBS sources by
scripts/build_patched_plugin.py, so that changing a Media Source's speed
time-stretches the audio instead of resampling it. Stock OBS plays a 1 kHz tone
at 150% as 1.5 kHz; with the patch it stays at 1 kHz.

The test records a Media Source through libobs and measures the tone in the
recording, so it fails if the bundle silently falls back to the stock plugin.
"""

from __future__ import annotations

import array
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

import pylibobs
from pylibobs import AudioEncoder, OBSContext, Output, Scene, Source, VideoEncoder
from pylibobs._ffi import get_lib
from pylibobs._lib import find_libobs, get_obs_module_dirs

pytestmark = pytest.mark.integration

TONE_HZ = 1000
SPEED_PERCENT = 150
RATE = 48000
#: 1.0 s of playback at 150%, so a 3 s recording crosses two loop boundaries —
#: that is where the filter is drained and the output trimmed to length.
CLIP_SECONDS = 1.5

_LIBS_DIR = Path(pylibobs.__file__).parent / "_libs"


def _bundled_plugin() -> Path | None:
    """obs-ffmpeg from *our* bundle, or None when libobs came from elsewhere."""
    plugin_dir = Path(get_obs_module_dirs()[0]).resolve()
    if _LIBS_DIR.resolve() not in plugin_dir.parents:
        return None            # system OBS / $LIBOBS_PATH — not ours to judge
    plugin = plugin_dir / "obs-ffmpeg.so"
    return plugin if plugin.is_file() else None


def _make_clip(path: str) -> None:
    # mpeg4/aac are libavcodec's own encoders, so this works with LGPL ffmpeg
    # builds too; the video codec is irrelevant to what is measured here.
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", f"color=black:s=320x180:r=30:d={CLIP_SECONDS}",
         "-f", "lavfi", "-i",
         f"sine=frequency={TONE_HZ}:duration={CLIP_SECONDS}:sample_rate={RATE}",
         "-c:v", "mpeg4", "-pix_fmt", "yuv420p", "-c:a", "aac", path],
        check=True, capture_output=True,
    )


def _tone_hz(path: str, skip_seconds: float = 0.5) -> float:
    """Estimate the dominant frequency by counting zero crossings of the tone."""
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "1",
         "-ar", str(RATE), "-f", "s16le", "-"],
        check=True, capture_output=True,
    ).stdout
    samples = array.array("h")
    samples.frombytes(raw[: len(raw) // 2 * 2])
    # Skip past encoder priming / source start and measure a window that is loud
    # enough to be the tone rather than silence.
    start = int(RATE * skip_seconds)
    window = samples[start:start + RATE]
    if not window or max(window, default=0) < 3000:
        return float("nan")
    crossings = sum(1 for a, b in zip(window, window[1:]) if (a < 0) != (b < 0))
    return crossings / 2 / (len(window) / RATE)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is needed to make and read the clip")
def test_media_source_speed_keeps_pitch(tmp_path):
    plugin = _bundled_plugin()
    if plugin is None:
        pytest.skip("libobs did not resolve to the bundled plugins (system OBS / $LIBOBS_PATH)")
    # Our own bundle carrying the stock plugin IS the regression this guards
    # against — e.g. re-running fetch_libs.py wipes the rebuilt one — so fail
    # rather than skip.
    assert b"atempo=" in plugin.read_bytes(), (
        f"{plugin} is the stock build: the Media Source will shift pitch with speed. "
        "Run 'python scripts/build_patched_plugin.py'."
    )

    clip = str(tmp_path / "tone.mp4")
    out_path = str(tmp_path / "recorded.mp4")
    _make_clip(clip)

    with OBSContext() as ctx:
        ctx.set_video(320, 180, fps_num=30)
        ctx.set_audio(samples_per_sec=RATE)
        ctx.load_modules()

        scene = Scene.create("main")
        media = Source.create("ffmpeg_source", "clip", {
            "is_local_file": True, "local_file": clip, "looping": True,
            "restart_on_activate": True, "speed_percent": SPEED_PERCENT,
        })
        scene.add(media)
        get_lib().obs_set_output_source(0, scene.as_source()._ptr)

        venc = VideoEncoder.create("obs_x264", "v",
                                   {"rate_control": "CRF", "crf": 30, "preset": "ultrafast"})
        aenc = AudioEncoder.create("ffmpeg_aac", "a", {"bitrate": 192})
        out = Output.create("mp4_output", "rec", {"path": out_path})
        out.set_video_encoder(venc)
        out.set_audio_encoder(aenc)

        assert out.start(), f"output.start() failed: {out.last_error}"
        time.sleep(3.0)
        assert out.total_frames > 0
        out.stop(wait=True)

    assert os.path.getsize(out_path) > 0
    measured = _tone_hz(out_path)
    assert measured == measured, "no audible tone in the recording"
    # Past two loop boundaries: the filter is drained and its output trimmed to
    # length at every EOF, so a regression there shows up here and not above.
    looped = _tone_hz(out_path, skip_seconds=2.4)
    assert looped == looped, "no audible tone after the loop point"
    # Stock behaviour would put this at TONE_HZ * SPEED_PERCENT / 100 = 1500 Hz.
    for label, value in (("start", measured), ("after looping", looped)):
        assert abs(value - TONE_HZ) < TONE_HZ * 0.08, (
            f"tone came out at {value:.0f} Hz {label} at {SPEED_PERCENT}% speed; "
            f"expected ~{TONE_HZ} Hz (pitch preserved), stock OBS gives "
            f"{TONE_HZ * SPEED_PERCENT // 100} Hz"
        )


def test_bundled_plugin_matches_libobs_version():
    """A plugin built against another OBS tag would be refused at load time."""
    import ctypes

    plugin_dir, _ = get_obs_module_dirs()
    plugin = os.path.join(plugin_dir, "obs-ffmpeg.so")
    if not os.path.isfile(plugin):
        pytest.skip("no bundled obs-ffmpeg")

    # libobs first, and globally: a plugin references its symbols and cannot be
    # loaded on its own.
    libobs = ctypes.CDLL(find_libobs(), mode=ctypes.RTLD_GLOBAL)
    libobs.obs_get_version.restype = ctypes.c_uint32

    module = ctypes.CDLL(plugin, mode=ctypes.RTLD_LOCAL)
    module.obs_module_ver.restype = ctypes.c_uint32
    plugin_ver = module.obs_module_ver()

    assert plugin_ver == libobs.obs_get_version(), (
        "bundled obs-ffmpeg was built against a different OBS version than the bundled libobs"
    )
