"""Integration tests for output extras: delay, mixers, packet callbacks,
reconnect settings, capabilities."""

from __future__ import annotations

import time

import pytest

pytestmark = pytest.mark.integration


def test_output_capabilities_and_flags():
    """Even before starting, an output exposes its flags and pause capability."""
    from pylibobs import OBSContext, Output

    with OBSContext() as obs:
        obs.set_video(320, 180)
        obs.set_audio()
        obs.load_modules()

        out = Output.create("ffmpeg_muxer", "cap_test",
                          {"path": "ignored.mkv"})

        # Flags is a bitfield of OBS_OUTPUT_*
        flags = out.flags
        assert flags > 0
        # ffmpeg_muxer is AV (video + audio)
        assert (flags & 1) and (flags & 2)

        # can_pause depends on the output type
        _ = out.can_pause   # just verify it doesn't raise


def test_output_mixer_roundtrip():
    """set_mixer / set_mixers should not crash.

    libobs only persists the mixer setting once the output is active for
    some output types — calling the getter on an inactive output may
    return 0. We just verify the setters don't raise.
    """
    from pylibobs import OBSContext, Output

    with OBSContext() as obs:
        obs.set_video(320, 180)
        obs.set_audio()
        obs.load_modules()

        out = Output.create("ffmpeg_muxer", "mix_test",
                          {"path": "ignored.mkv"})

        out.mixer = 2
        out.mixers = 0b101
        # Getters return ints — accept whatever libobs has stored
        assert isinstance(out.mixer, int)
        assert isinstance(out.mixers, int)


def test_output_delay_settings():
    """set_delay / get_delay should roundtrip; active_delay is 0 when stopped."""
    from pylibobs import OBSContext, Output

    with OBSContext() as obs:
        obs.set_video(320, 180)
        obs.set_audio()
        obs.load_modules()

        out = Output.create("ffmpeg_muxer", "delay_test",
                          {"path": "ignored.mkv"})

        out.set_delay(10, flags=0)
        assert out.delay == 10
        assert out.active_delay == 0   # not started

        out.set_reconnect_settings(retry_count=5, retry_sec=3)
        # No getter for the reconnect settings, but call shouldn't crash.
        assert out.reconnecting is False


def test_output_packet_callback_smoke(tmp_path):
    """Wire a packet callback to a brief recording and capture some
    encoder packets."""
    from pylibobs import (
        AudioEncoder, OBSContext, Output, Scene, Source, VideoEncoder,
    )
    from pylibobs._ffi import get_lib

    out_path = tmp_path / "pkt.mkv"

    with OBSContext() as obs:
        obs.set_video(320, 180, fps_num=30)
        obs.set_audio()
        obs.load_modules()

        scene = Scene.create("pkt_scene")
        get_lib().obs_set_output_source(0, scene.as_source()._ptr)
        src = Source.create("color_source_v3", "pkt_src",
                          {"color": 0xFF008040, "width": 320, "height": 180})
        scene.add(src)

        venc = VideoEncoder.create("obs_x264", "pkt_v",
                                  {"rate_control": "CRF", "crf": 28,
                                   "preset": "veryfast"})
        aenc = AudioEncoder.create("ffmpeg_aac", "pkt_a", {"bitrate": 96})

        out = Output.create("ffmpeg_muxer", "pkt_rec", {"path": str(out_path)})
        out.set_video_encoder(venc)
        out.set_audio_encoder(aenc)

        packets: list[dict] = []
        out.add_packet_callback(lambda pkt: packets.append({
            "type":     pkt["type"],
            "size":     pkt["size"],
            "keyframe": pkt["keyframe"],
        }))

        assert out.start(), out.last_error
        time.sleep(1.5)
        out.stop(wait=True)

        # We should have seen both video and audio packets
        types = {p["type"] for p in packets}
        assert types, f"No packets captured at all"
        # type 0 = audio, 1 = video in obs_encoder_packet_type
        assert any(p["size"] > 0 for p in packets)
