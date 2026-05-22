"""
Raw frame / audio capture callbacks — the bridge between libobs and NumPy.

Three kinds of callbacks:

  1. Per-source audio capture
       Source.add_audio_capture_callback(fn) → fn(samples, frames, sample_rate, muted)
       `samples` is a list of bytes objects, one per channel. Cast with
       numpy.frombuffer(samples[0], dtype=np.float32) for libobs's float planar
       PCM format.

  2. Global post-mix audio
       add_raw_audio_callback(mix_idx=0, fn=...)
       Same payload format as the per-source callback but post-mix.

  3. Global post-render video
       add_raw_video_callback(fn, format=NV12, width=None, height=None)
       fn receives (data_pointers_list, linesize_list, width, height,
       format_int, timestamp_ns). Convert via numpy.frombuffer(...) on each
       plane pointer. With `format`/`width`/`height` set you can request a
       conversion (e.g. NV12 → BGRA).

  4. Render hooks
       add_main_render_callback(fn) → fn(canvas_cx, canvas_cy) called every
       frame on the graphics thread. Use this to inject custom rendering.
       add_tick_callback(fn) → fn(seconds_since_last_tick) on the video tick.

All callbacks run on libobs threads, so keep them short. They never see
the GIL until cffi acquires it — if you need to do heavy work, post to a
queue and return.
"""

from __future__ import annotations

import threading
from typing import Callable

from ._ffi import ffi, get_lib

_MAX_PLANES = 8     # libobs MAX_AV_PLANES
_BYTES_PER_SAMPLE = 4   # libobs's mixed audio is always float32 planar


# ---------------------------------------------------------------------------
# Keep cffi callback trampolines alive — libobs holds raw function pointers.
# ---------------------------------------------------------------------------
_alive: dict[str, set] = {
    "audio_src": set(),
    "audio_mix": set(),
    "video":     set(),
    "render":    set(),
    "tick":      set(),
}
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Channel-count introspection.
#
# libobs's `struct audio_data` has data[MAX_AV_PLANES] but only the first
# `channels` entries are valid pointers. Indexes [channels..MAX_AV_PLANES-1]
# contain uninitialised garbage — they are NOT guaranteed to be NULL, so
# iterating all 8 and dereferencing each "non-NULL" entry causes segfaults.
#
# Resolve the true channel count once at registration time. Callers can
# override via `channels=N` if they want a specific count.
# ---------------------------------------------------------------------------
def _resolve_global_channel_count() -> int:
    lib = get_lib()
    ao = lib.obs_get_audio()
    if ao == ffi.NULL:
        return 2     # default to stereo
    ch = int(lib.audio_output_get_channels(ao))
    return max(1, min(ch, _MAX_PLANES))


def _resolve_source_channel_count(source) -> int:
    lib = get_lib()
    layout = int(lib.obs_source_get_speaker_layout(source._ptr))
    # speaker_layout enum: MONO=1, STEREO=2, 2P1=3, 4P0=4, 4P1=5, 5P1=6, 7P1=8
    # Numeric values are 0..6,8 with the same channel counts.
    layout_to_channels = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 8: 8}
    ch = layout_to_channels.get(layout, 0)
    if ch <= 0:
        # Fall back to the global mix's channel count if the source's
        # layout is UNKNOWN (some sources report this before their first
        # audio frame).
        return _resolve_global_channel_count()
    return min(ch, _MAX_PLANES)


def _read_planes(data_ptrs, sizes_or_linesizes) -> list[bytes]:
    """Copy the non-NULL planes pointed to by `data_ptrs` into Python bytes.

    `sizes_or_linesizes` is a list of byte counts per plane. We copy because
    libobs may reuse the underlying buffer the moment our callback returns.
    """
    out: list[bytes] = []
    for i in range(_MAX_PLANES):
        ptr = data_ptrs[i]
        size = int(sizes_or_linesizes[i]) if sizes_or_linesizes else 0
        if ptr == ffi.NULL or size <= 0:
            out.append(b"")
        else:
            out.append(bytes(ffi.buffer(ptr, size)))
    return out


# ---------------------------------------------------------------------------
# Per-source audio capture
# ---------------------------------------------------------------------------
def add_source_audio_capture_callback(
    source,
    fn: Callable[[list[bytes], int, int, bool], None],
    *,
    channels: int | None = None,
) -> object:
    """Attach a Python audio-frame listener to `source`.

    `fn(planes, frames, timestamp_ns, muted)`:
      - planes: list of `channels` `bytes` objects (planar float32 PCM)
      - frames: number of samples per channel in this batch
      - timestamp_ns: monotonic timestamp
      - muted: True when libobs mixed silence (still passes a buffer)

    `channels` defaults to the source's speaker-layout channel count
    (falls back to the global mix). Passing `channels=2` forces stereo.

    libobs's `struct audio_data` has 8 plane slots but only the first
    `channels` are valid pointers — the rest contain uninitialised garbage.
    Iterating all 8 and dereferencing the not-NULL-looking ones segfaults.
    This wrapper only iterates the resolved channel count.

    Returns a handle you can pass to `remove_source_audio_capture_callback`.
    """
    lib = get_lib()

    if channels is None:
        n_ch = _resolve_source_channel_count(source)
    else:
        n_ch = max(1, min(int(channels), _MAX_PLANES))

    @ffi.callback("void(void *, obs_source_t *, const struct audio_data *, bool)")
    def _trampoline(_param, _src, audio, muted):
        try:
            frames = int(audio.frames)
            plane_size = frames * _BYTES_PER_SAMPLE
            planes: list[bytes] = []
            for i in range(n_ch):
                p = audio.data[i]
                if p == ffi.NULL:
                    planes.append(b"")
                else:
                    planes.append(bytes(ffi.buffer(p, plane_size)))
            fn(planes, frames, int(audio.timestamp), bool(muted))
        except Exception:
            pass

    with _lock:
        _alive["audio_src"].add(_trampoline)
    lib.obs_source_add_audio_capture_callback(source._ptr, _trampoline, ffi.NULL)
    return _trampoline


def remove_source_audio_capture_callback(source, handle) -> None:
    lib = get_lib()
    lib.obs_source_remove_audio_capture_callback(source._ptr, handle, ffi.NULL)
    with _lock:
        _alive["audio_src"].discard(handle)


# ---------------------------------------------------------------------------
# Global raw audio (post-mix)
# ---------------------------------------------------------------------------
def add_raw_audio_callback(
    fn: Callable[[int, list[bytes], int, int], None],
    mix_idx: int = 0,
    *,
    channels: int | None = None,
) -> object:
    """Attach a Python listener to the global mixed audio output.

    `fn(mix_idx, planes, frames, timestamp_ns)` — `planes` is a list of
    `channels` `bytes` objects (planar float32 PCM, one per channel).
    `mix_idx` is the audio mixer track (0–5).

    `channels` defaults to `audio_output_get_channels(obs_get_audio())`
    (the active speaker layout's channel count, typically 2 for stereo).
    Pass `channels=2` to force stereo, or any other count if you've
    reconfigured libobs's audio.

    Why this matters: libobs's `struct audio_data` has 8 plane slots
    (`data[MAX_AV_PLANES]`) but only the first `channels` are valid
    pointers. Indexes past `channels` contain whatever garbage was at
    that struct slot — they're NOT guaranteed NULL, so iterating all 8
    and dereferencing the non-NULL-looking ones causes segfaults. The
    fix is to only iterate the actual channel count.
    """
    lib = get_lib()

    if channels is None:
        n_ch = _resolve_global_channel_count()
    else:
        n_ch = max(1, min(int(channels), _MAX_PLANES))

    @ffi.callback("void(void *, size_t, struct audio_data *)")
    def _trampoline(_param, mix, audio):
        try:
            frames = int(audio.frames)
            plane_size = frames * _BYTES_PER_SAMPLE
            planes: list[bytes] = []
            for i in range(n_ch):
                p = audio.data[i]
                if p == ffi.NULL:
                    planes.append(b"")
                else:
                    planes.append(bytes(ffi.buffer(p, plane_size)))
            fn(int(mix), planes, frames, int(audio.timestamp))
        except Exception:
            pass

    with _lock:
        _alive["audio_mix"].add(_trampoline)
    lib.obs_add_raw_audio_callback(int(mix_idx), ffi.NULL, _trampoline, ffi.NULL)
    return _trampoline


def remove_raw_audio_callback(handle, mix_idx: int = 0) -> None:
    lib = get_lib()
    lib.obs_remove_raw_audio_callback(int(mix_idx), handle, ffi.NULL)
    with _lock:
        _alive["audio_mix"].discard(handle)


# ---------------------------------------------------------------------------
# Global raw video (post-render)
# ---------------------------------------------------------------------------
def add_raw_video_callback(
    fn: Callable[[list[bytes], list[int], int, int, int, int], None],
    format: int | None = None,
    width: int | None = None,
    height: int | None = None,
) -> object:
    """Attach a Python listener for rendered video frames.

    `fn(planes, linesizes, width, height, format, timestamp_ns)`:
      - planes: list of 8 `bytes` objects, one per plane (NV12 has Y in [0]
        and interleaved UV in [1]; BGRA has all data in [0])
      - linesizes: list of 8 stride values; planes with linesize 0 are unused
      - width / height: pixel dimensions
      - format: a `pylibobs.VideoFormat` int
      - timestamp_ns: monotonic timestamp

    If `format`/`width`/`height` are provided, libobs will convert frames
    into that format for you (e.g. NV12→BGRA for direct numpy use).
    """
    lib = get_lib()

    out_w = width  if width  is not None else 0
    out_h = height if height is not None else 0
    out_f = format if format is not None else 0

    @ffi.callback("void(void *, struct video_data *)")
    def _trampoline(_param, frame):
        try:
            # We don't know the height for plane sizing without struct
            # video_output_info; approximate plane size from linesize*height
            # provided by the caller, or fall back to linesize*1080 max.
            h = out_h if out_h else 1080
            planes: list[bytes] = []
            linesizes: list[int] = []
            for i in range(_MAX_PLANES):
                ls = int(frame.linesize[i])
                p  = frame.data[i]
                linesizes.append(ls)
                if p == ffi.NULL or ls == 0:
                    planes.append(b"")
                else:
                    planes.append(bytes(ffi.buffer(p, ls * h)))
            fn(planes, linesizes, out_w, out_h, out_f, int(frame.timestamp))
        except Exception:
            pass

    # Build the conversion struct if any was requested
    if out_f or out_w or out_h:
        conv = ffi.new("struct video_scale_info *")
        conv.format     = out_f or 5    # GS_BGRA fallback
        conv.width      = out_w
        conv.height     = out_h
        conv.range      = 0
        conv.colorspace = 0
        lib.obs_add_raw_video_callback(conv, _trampoline, ffi.NULL)
    else:
        lib.obs_add_raw_video_callback(ffi.NULL, _trampoline, ffi.NULL)

    with _lock:
        _alive["video"].add(_trampoline)
    return _trampoline


def remove_raw_video_callback(handle) -> None:
    lib = get_lib()
    lib.obs_remove_raw_video_callback(handle, ffi.NULL)
    with _lock:
        _alive["video"].discard(handle)


# ---------------------------------------------------------------------------
# Main render / tick hooks
# ---------------------------------------------------------------------------
def add_main_render_callback(
    fn: Callable[[int, int], None],
) -> object:
    """Run `fn(cx, cy)` on the graphics thread every rendered frame.

    Use this if you want to inject custom rendering into the main canvas
    (e.g. draw overlays via gs_* calls). Keep the work small — it runs
    on the gfx thread.
    """
    lib = get_lib()

    @ffi.callback("void(void *, uint32_t, uint32_t)")
    def _trampoline(_param, cx, cy):
        try:
            fn(int(cx), int(cy))
        except Exception:
            pass

    with _lock:
        _alive["render"].add(_trampoline)
    lib.obs_add_main_render_callback(_trampoline, ffi.NULL)
    return _trampoline


def remove_main_render_callback(handle) -> None:
    lib = get_lib()
    lib.obs_remove_main_render_callback(handle, ffi.NULL)
    with _lock:
        _alive["render"].discard(handle)


def add_tick_callback(fn: Callable[[float], None]) -> object:
    """Run `fn(seconds_since_last_tick)` on every video tick."""
    lib = get_lib()

    @ffi.callback("void(void *, float)")
    def _trampoline(_param, seconds):
        try:
            fn(float(seconds))
        except Exception:
            pass

    with _lock:
        _alive["tick"].add(_trampoline)
    lib.obs_add_tick_callback(_trampoline, ffi.NULL)
    return _trampoline


def remove_tick_callback(handle) -> None:
    lib = get_lib()
    lib.obs_remove_tick_callback(handle, ffi.NULL)
    with _lock:
        _alive["tick"].discard(handle)


def clear_all_callbacks() -> None:
    """Disconnect every registered callback. Useful for clean test teardown."""
    lib = get_lib()
    with _lock:
        for h in list(_alive["video"]):
            try: lib.obs_remove_raw_video_callback(h, ffi.NULL)
            except Exception: pass
        for h in list(_alive["render"]):
            try: lib.obs_remove_main_render_callback(h, ffi.NULL)
            except Exception: pass
        for h in list(_alive["tick"]):
            try: lib.obs_remove_tick_callback(h, ffi.NULL)
            except Exception: pass
        # Per-source / per-mix callbacks need the original source/mix idx;
        # we can't blindly remove them.
        for k in _alive: _alive[k].clear()
