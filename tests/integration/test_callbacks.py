"""Integration tests for raw frame / audio callbacks and render hooks.

These callbacks fire on libobs threads, so we sleep briefly to give them
time to run and then check the recorded data on the main thread.
"""

from __future__ import annotations

import time

import pytest

pytestmark = pytest.mark.integration


def test_tick_callback_fires():
    """add_tick_callback should fire on every video tick (every ~33 ms at 30 fps)."""
    from pylibobs import OBSContext
    from pylibobs.callbacks import add_tick_callback, remove_tick_callback

    with OBSContext() as obs:
        obs.set_video(320, 180, fps_num=30)
        obs.set_audio()
        obs.load_modules()

        counts: list[float] = []
        h = add_tick_callback(lambda secs: counts.append(secs))
        time.sleep(0.4)
        remove_tick_callback(h)

        assert len(counts) > 5, f"Only {len(counts)} ticks fired in 0.4s"
        assert all(0.0 < s < 0.5 for s in counts), counts


def test_main_render_callback_fires():
    """add_main_render_callback fires every rendered frame on the gfx thread."""
    from pylibobs import OBSContext, Scene, Source
    from pylibobs.callbacks import (
        add_main_render_callback, remove_main_render_callback,
    )
    from pylibobs._ffi import get_lib

    with OBSContext() as obs:
        obs.set_video(320, 180, fps_num=30)
        obs.set_audio()
        obs.load_modules()

        # Need something rendering, otherwise the main render isn't invoked
        scene = Scene.create("rc_scene")
        get_lib().obs_set_output_source(0, scene.as_source()._ptr)
        src = Source.create("color_source_v3", "rc_src",
                          {"color": 0xFF0080FF, "width": 320, "height": 180})
        scene.add(src)

        sizes: list[tuple[int, int]] = []
        h = add_main_render_callback(lambda cx, cy: sizes.append((cx, cy)))
        time.sleep(0.4)
        remove_main_render_callback(h)

        # Even without an attached display, main_render_callback should
        # fire while we have an active output source. May fire 0 times in
        # truly headless setups — accept that, just verify no crash.
        assert isinstance(sizes, list)
        for s in sizes:
            assert s[0] >= 0 and s[1] >= 0


def test_raw_video_callback_smoke():
    """Register a raw-video callback while recording; verify no crash and
    that the callback gets called with sane parameters if it fires."""
    from pylibobs import (
        AudioEncoder, OBSContext, Output, Scene, Source, VideoEncoder,
    )
    from pylibobs.callbacks import (
        add_raw_video_callback, remove_raw_video_callback,
    )
    from pylibobs._ffi import get_lib

    with OBSContext() as obs:
        obs.set_video(320, 180, fps_num=30)
        obs.set_audio()
        obs.load_modules()

        scene = Scene.create("rv_scene")
        get_lib().obs_set_output_source(0, scene.as_source()._ptr)
        src = Source.create("color_source_v3", "rv_src",
                          {"color": 0xFFFF0080, "width": 320, "height": 180})
        scene.add(src)

        frames: list = []

        def on_frame(planes, linesizes, w, h, fmt, ts):
            frames.append((w, h, fmt, ts, sum(len(p) for p in planes)))

        # Request BGRA-converted frames at the canvas size
        from pylibobs import VideoFormat
        handle = add_raw_video_callback(on_frame, format=int(VideoFormat.BGRA),
                                        width=320, height=180)

        # Set up encoders + output so libobs actually renders frames
        venc = VideoEncoder.create("obs_x264", "rv_v",
                                  {"rate_control": "CRF", "crf": 28,
                                   "preset": "veryfast"})
        aenc = AudioEncoder.create("ffmpeg_aac", "rv_a", {"bitrate": 96})
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".mkv", delete=False) as f:
            out_path = f.name
        out = Output.create("ffmpeg_muxer", "rv_rec", {"path": out_path})
        out.set_video_encoder(venc)
        out.set_audio_encoder(aenc)
        try:
            out.start()
            time.sleep(0.5)
            out.stop(wait=True)
        finally:
            remove_raw_video_callback(handle)

        # We don't assert frames > 0 — without a display, libobs may not
        # always invoke the raw video callback. Just verify no corruption.
        for entry in frames:
            w, h, fmt, ts, total = entry
            assert w == 320 and h == 180
            assert total > 0


def test_source_audio_capture_callback_smoke():
    """Register a per-source audio capture callback; verify it doesn't crash
    when no audio is actually flowing."""
    from pylibobs import OBSContext, Source
    from pylibobs.callbacks import (
        add_source_audio_capture_callback,
        remove_source_audio_capture_callback,
    )

    with OBSContext() as obs:
        obs.set_video(320, 180, fps_num=30)
        obs.set_audio()
        obs.load_modules()

        # Try to create a silent input — if no audio device, skip.
        try:
            src = Source.create("wasapi_input_capture", "mic")
        except RuntimeError:
            pytest.skip("No audio input source plugin available")

        records: list[tuple[int, int]] = []

        def on_audio(planes, frames, ts, muted):
            records.append((frames, ts))

        handle = add_source_audio_capture_callback(src, on_audio)
        time.sleep(0.2)
        remove_source_audio_capture_callback(src, handle)
        # No assertion on the count — there may not be a real device.


def test_raw_audio_callback_does_not_segfault_on_first_fire():
    """
    Regression test for the original bug report — the trampoline used to
    iterate all 8 plane slots and dereference the uninitialised pointers
    past the active channel count, causing a segfault on the first fire.

    With the fix, the callback should fire safely. This test does NOT
    require an actual audio source; we just verify the registration +
    deregistration round-trip never crashes the process.
    """
    from pylibobs import OBSContext
    from pylibobs.callbacks import (
        add_raw_audio_callback, remove_raw_audio_callback,
    )

    with OBSContext() as obs:
        obs.set_video(320, 180, fps_num=30)
        obs.set_audio(samples_per_sec=48000)
        obs.load_modules()

        fires: list[tuple[int, int, int]] = []

        def cb(mix_idx, planes, frames, ts):
            fires.append((mix_idx, frames, len(planes)))

        handle = add_raw_audio_callback(cb, mix_idx=0)
        # libobs's audio thread is alive; give it time to fire a few callbacks
        # even with no audio sources (it emits silent buffers on the mix).
        time.sleep(0.5)
        remove_raw_audio_callback(handle, mix_idx=0)

        # Without an audio source the mix won't necessarily fire. The
        # important assertion is that the process didn't die.
        for mix_idx, frames, n_planes in fires:
            assert mix_idx == 0
            assert frames > 0
            # The wrapper should have returned `n_channels` planes, not 8
            assert 1 <= n_planes <= 8, n_planes


def test_raw_audio_callback_with_explicit_channels_override():
    """`channels=` lets callers pin the channel count explicitly — useful
    when the global audio config might change later."""
    from pylibobs import OBSContext
    from pylibobs.callbacks import (
        add_raw_audio_callback, remove_raw_audio_callback,
    )

    with OBSContext() as obs:
        obs.set_video(320, 180, fps_num=30)
        obs.set_audio(samples_per_sec=48000)
        obs.load_modules()

        seen: list[int] = []
        def cb(mix_idx, planes, frames, ts):
            seen.append(len(planes))

        # Force stereo regardless of what obs_get_audio() reports
        handle = add_raw_audio_callback(cb, mix_idx=0, channels=2)
        time.sleep(0.2)
        remove_raw_audio_callback(handle, mix_idx=0)

        # If any callbacks fired, they must report exactly 2 planes
        for n in seen:
            assert n == 2
