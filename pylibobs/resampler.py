"""
AudioResampler — wraps `audio_resampler_t` for standalone sample-rate /
audio-format / channel-layout conversion.

This is libobs's internal resampler exposed as a self-contained utility.
It does NOT require `obs_startup()` — you can use it independently.

Common use cases:
  * 48 kHz stereo → 16 kHz mono for speech-recognition / wake-word models
  * 44.1 kHz → 48 kHz for matching libobs's mix to a different output
  * planar float → interleaved int16 for sending to a non-OBS encoder

Example::

    from pylibobs import AudioFormat, Speakers
    from pylibobs.resampler import AudioResampler

    rs = AudioResampler(
        in_rate=48000, in_format=AudioFormat.FLOAT_PLANAR, in_layout=Speakers.STEREO,
        out_rate=16000, out_format=AudioFormat.FLOAT_PLANAR, out_layout=Speakers.MONO,
    )

    out_planes, out_frames = rs.resample(planes_in, frames_in)
    # out_planes is list[bytes], one per output channel
"""

from __future__ import annotations

from enum import IntEnum

from ._ffi import ffi, get_lib


class AudioFormat(IntEnum):
    UNKNOWN      = 0
    U8BIT        = 1   # 8-bit unsigned, interleaved
    S16BIT       = 2   # 16-bit signed, interleaved
    S32BIT       = 3   # 32-bit signed, interleaved
    FLOAT        = 4   # float32, interleaved
    U8BIT_PLANAR = 5
    S16BIT_PLANAR= 6
    S32BIT_PLANAR= 7
    FLOAT_PLANAR = 8


# Bytes per sample for each format (one channel's worth)
_BYTES_PER_SAMPLE = {
    AudioFormat.U8BIT:         1,
    AudioFormat.S16BIT:        2,
    AudioFormat.S32BIT:        4,
    AudioFormat.FLOAT:         4,
    AudioFormat.U8BIT_PLANAR:  1,
    AudioFormat.S16BIT_PLANAR: 2,
    AudioFormat.S32BIT_PLANAR: 4,
    AudioFormat.FLOAT_PLANAR:  4,
}

# Whether a format is planar (one buffer per channel) vs interleaved
_IS_PLANAR = {
    AudioFormat.U8BIT_PLANAR, AudioFormat.S16BIT_PLANAR,
    AudioFormat.S32BIT_PLANAR, AudioFormat.FLOAT_PLANAR,
}

# Map speaker_layout enum to channel count (matches libobs's enum values)
_LAYOUT_CHANNELS = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 8: 8}


class AudioResampler:
    """Wrap an audio_resampler_t. Resample arbitrary buffers between
    sample rate / format / channel layout combinations."""

    __slots__ = ("_ptr", "_in_fmt", "_in_layout", "_out_fmt", "_out_layout",
                 "_in_channels", "_out_channels", "_in_bps", "_out_bps")

    def __init__(
        self,
        *,
        in_rate: int,
        in_format: AudioFormat,
        in_layout,        # speaker_layout int or pylibobs.Speakers
        out_rate: int,
        out_format: AudioFormat,
        out_layout,
    ) -> None:
        lib = get_lib()

        src = ffi.new("struct resample_info *")
        src.samples_per_sec = int(in_rate)
        src.format          = int(in_format)
        src.speakers        = int(in_layout)

        dst = ffi.new("struct resample_info *")
        dst.samples_per_sec = int(out_rate)
        dst.format          = int(out_format)
        dst.speakers        = int(out_layout)

        ptr = lib.audio_resampler_create(dst, src)
        if ptr == ffi.NULL:
            raise RuntimeError(
                "audio_resampler_create returned NULL — check format/layout. "
                f"Source: {in_rate} Hz / {AudioFormat(in_format).name} / "
                f"{int(in_layout)} ch.  Dest: {out_rate} Hz / "
                f"{AudioFormat(out_format).name} / {int(out_layout)} ch."
            )

        self._ptr        = ptr
        self._in_fmt     = AudioFormat(int(in_format))
        self._out_fmt    = AudioFormat(int(out_format))
        self._in_layout  = int(in_layout)
        self._out_layout = int(out_layout)
        self._in_channels  = _LAYOUT_CHANNELS.get(self._in_layout, 0) or 2
        self._out_channels = _LAYOUT_CHANNELS.get(self._out_layout, 0) or 2
        self._in_bps  = _BYTES_PER_SAMPLE[self._in_fmt]
        self._out_bps = _BYTES_PER_SAMPLE[self._out_fmt]

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    @property
    def in_channels(self) -> int:
        return self._in_channels

    @property
    def out_channels(self) -> int:
        return self._out_channels

    @property
    def in_format(self) -> AudioFormat:
        return self._in_fmt

    @property
    def out_format(self) -> AudioFormat:
        return self._out_fmt

    # ------------------------------------------------------------------
    # Resample one input batch
    # ------------------------------------------------------------------
    def resample(
        self,
        planes: list[bytes] | bytes,
        frames: int,
        ts_offset_ns: int = 0,
    ) -> tuple[list[bytes], int, int]:
        """Convert `frames` of input audio.

        For PLANAR input, pass a list of `in_channels` `bytes` objects, each
        of length `frames * bytes_per_sample`.

        For INTERLEAVED input, pass a single `bytes` object containing
        `frames * in_channels * bytes_per_sample` bytes — it will be wrapped
        as `[bytes_obj]` (libobs's resampler always uses data[0] for
        interleaved formats).

        Returns ``(out_planes, out_frames, ts_offset_ns)`` where
        ``out_planes`` is a list of `out_channels` `bytes` objects.
        """
        lib = get_lib()
        if isinstance(planes, (bytes, bytearray, memoryview)):
            planes = [bytes(planes)]
        else:
            planes = [bytes(p) for p in planes]

        # Allocate cffi arrays. libobs wants `const uint8_t * const *input`.
        in_keepalive: list = []   # keep input ffi buffers alive
        in_arr = ffi.new("const uint8_t *[8]")
        for i in range(8):
            if i < len(planes) and len(planes[i]) > 0:
                buf = ffi.new("uint8_t[]", planes[i])
                in_keepalive.append(buf)
                in_arr[i] = buf
            else:
                in_arr[i] = ffi.NULL

        out_arr = ffi.new("uint8_t *[8]")
        out_frames = ffi.new("uint32_t *")
        ts_offset = ffi.new("uint64_t *", int(ts_offset_ns))

        ok = lib.audio_resampler_resample(
            self._ptr, out_arr, out_frames, ts_offset, in_arr, int(frames),
        )
        if not ok:
            raise RuntimeError("audio_resampler_resample returned false")

        n = int(out_frames[0])
        # The output planes belong to the resampler — copy them out so the
        # caller can safely keep them past the next resample() call.
        out_planes: list[bytes] = []
        if self._out_fmt in _IS_PLANAR:
            plane_bytes = n * self._out_bps
            for i in range(self._out_channels):
                ptr = out_arr[i]
                out_planes.append(
                    bytes(ffi.buffer(ptr, plane_bytes)) if ptr != ffi.NULL else b""
                )
        else:
            # Interleaved: everything lives in data[0]
            total_bytes = n * self._out_bps * self._out_channels
            ptr = out_arr[0]
            out_planes.append(
                bytes(ffi.buffer(ptr, total_bytes)) if ptr != ffi.NULL else b""
            )

        return out_planes, n, int(ts_offset[0])

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def release(self) -> None:
        if self._ptr != ffi.NULL:
            try:
                get_lib().audio_resampler_destroy(self._ptr)
            except Exception:
                pass
            self._ptr = ffi.NULL

    def __del__(self) -> None:
        try: self.release()
        except Exception: pass

    def __enter__(self) -> "AudioResampler":
        return self

    def __exit__(self, *_) -> None:
        self.release()

    def __repr__(self) -> str:
        return (f"AudioResampler({self._in_fmt.name}/{self._in_channels}ch "
                f"→ {self._out_fmt.name}/{self._out_channels}ch)")
