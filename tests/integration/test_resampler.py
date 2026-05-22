"""Integration tests for the standalone audio resampler."""

from __future__ import annotations

import math
import struct

import pytest

pytestmark = pytest.mark.integration


def _make_sine_wave_planar_f32(
    freq_hz: float, duration_s: float, sample_rate: int, channels: int,
) -> list[bytes]:
    """Synthesize `channels` planar buffers of a sine wave at `freq_hz`."""
    n = int(duration_s * sample_rate)
    samples = [
        math.sin(2 * math.pi * freq_hz * i / sample_rate)
        for i in range(n)
    ]
    one_plane = struct.pack(f"<{n}f", *samples)
    return [one_plane for _ in range(channels)]


def test_resampler_48k_stereo_to_16k_mono():
    """The canonical 'feed a speech model' downsample."""
    from pylibobs import AudioFormat, Speakers
    from pylibobs.resampler import AudioResampler

    in_rate, out_rate = 48000, 16000
    duration = 0.05  # 50 ms
    in_frames = int(in_rate * duration)
    planes_in = _make_sine_wave_planar_f32(440.0, duration, in_rate, 2)

    with AudioResampler(
        in_rate=in_rate, in_format=AudioFormat.FLOAT_PLANAR, in_layout=Speakers.STEREO,
        out_rate=out_rate, out_format=AudioFormat.FLOAT_PLANAR, out_layout=Speakers.MONO,
    ) as rs:
        out_planes, out_frames, _ = rs.resample(planes_in, in_frames)

    # 48k → 16k: expect 1/3 of the input frames. The resampler has an
    # inherent filter-delay of a few samples — libobs's SOX-style resampler
    # typically swallows ~16-32 samples on first call, so allow ~5% slack.
    expected = in_frames // 3
    assert abs(out_frames - expected) <= max(32, expected // 20), (
        f"expected ~{expected} frames, got {out_frames}"
    )
    # Mono output → 1 plane, each frame is 4 bytes
    assert len(out_planes) == 1
    assert len(out_planes[0]) == out_frames * 4


def test_resampler_no_op_same_rate_same_format():
    """Same rate / same format should pass through with matching frame count."""
    from pylibobs import AudioFormat, Speakers
    from pylibobs.resampler import AudioResampler

    in_frames = 1024
    planes_in = _make_sine_wave_planar_f32(1000.0, in_frames / 48000.0, 48000, 2)

    with AudioResampler(
        in_rate=48000, in_format=AudioFormat.FLOAT_PLANAR, in_layout=Speakers.STEREO,
        out_rate=48000, out_format=AudioFormat.FLOAT_PLANAR, out_layout=Speakers.STEREO,
    ) as rs:
        out_planes, out_frames, _ = rs.resample(planes_in, in_frames)

    # No-op shouldn't expand or shrink
    assert abs(out_frames - in_frames) <= 2
    assert len(out_planes) == 2   # stereo → 2 planes
    # Channels are independent — both should be ~equal length
    assert len(out_planes[0]) == len(out_planes[1])


def test_resampler_float_planar_to_interleaved_int16():
    """Convert planar float to interleaved int16 — useful for sending to
    a non-OBS audio sink that wants packed S16."""
    from pylibobs import AudioFormat, Speakers
    from pylibobs.resampler import AudioResampler

    in_frames = 2048
    planes_in = _make_sine_wave_planar_f32(440.0, in_frames / 48000.0, 48000, 2)

    with AudioResampler(
        in_rate=48000, in_format=AudioFormat.FLOAT_PLANAR, in_layout=Speakers.STEREO,
        out_rate=48000, out_format=AudioFormat.S16BIT, out_layout=Speakers.STEREO,
    ) as rs:
        out_planes, out_frames, _ = rs.resample(planes_in, in_frames)

    # Interleaved → single plane with 2 channels of int16
    assert len(out_planes) == 1
    assert len(out_planes[0]) == out_frames * 2 * 2   # frames * ch * 2 bytes


def test_resampler_repeated_calls_share_no_state():
    """Calling resample() many times shouldn't leak or corrupt the resampler."""
    from pylibobs import AudioFormat, Speakers
    from pylibobs.resampler import AudioResampler

    with AudioResampler(
        in_rate=48000, in_format=AudioFormat.FLOAT_PLANAR, in_layout=Speakers.STEREO,
        out_rate=16000, out_format=AudioFormat.FLOAT_PLANAR, out_layout=Speakers.MONO,
    ) as rs:
        for batch in range(20):
            planes = _make_sine_wave_planar_f32(440.0, 0.01, 48000, 2)
            out_planes, out_frames, _ = rs.resample(planes, 480)
            assert out_frames > 0
            assert len(out_planes) == 1
