"""Integration tests for video timing / HDR / state introspection."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_video_frame_time_advances():
    """obs_get_video_frame_time should return a monotonically advancing ns timestamp."""
    import time
    from pylibobs import OBSContext

    with OBSContext() as obs:
        obs.set_video(320, 180, fps_num=30)
        obs.set_audio()

        t1 = obs.video_frame_time_ns
        time.sleep(0.1)
        t2 = obs.video_frame_time_ns
        # 100 ms ≥ 50 ms of frame time
        assert t2 > t1, f"video time didn't advance: {t1} -> {t2}"


def test_get_current_video_info_matches_set():
    """get_current_video_info should reflect what we passed to set_video."""
    from pylibobs import OBSContext, VideoFormat

    with OBSContext() as obs:
        obs.set_video(width=1280, height=720, fps_num=60, fps_den=1,
                      output_format=VideoFormat.NV12)
        obs.set_audio()

        info = obs.get_current_video_info()
        assert info is not None
        assert info["base_width"] == 1280
        assert info["base_height"] == 720
        assert info["fps_num"] == 60
        assert info["fps_den"] == 1
        assert info["output_format"] == int(VideoFormat.NV12)
        assert info["gpu_conversion"] is True


def test_hdr_levels_getters_and_setters():
    """SDR/HDR getters return non-negative floats; setters round-trip."""
    from pylibobs import OBSContext

    with OBSContext() as obs:
        obs.set_video(320, 180)
        obs.set_audio()

        # Defaults can be 0 if uninitialised — set known values first.
        obs.set_video_levels(sdr_white=300.0, hdr_nominal_peak=1000.0)
        sdr = obs.sdr_white_level
        hdr = obs.hdr_nominal_peak_level
        assert sdr == pytest.approx(300.0, abs=1.0)
        assert hdr == pytest.approx(1000.0, abs=1.0)


def test_reset_audio_monitoring_doesnt_crash():
    """reset_audio_monitoring re-enumerates audio output devices."""
    from pylibobs import OBSContext

    with OBSContext() as obs:
        obs.set_video(320, 180)
        obs.set_audio()
        obs.reset_audio_monitoring()
        # No assertion — just verify the call doesn't crash
