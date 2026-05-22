"""
MediaRemux — lossless container conversion (e.g. MKV ↔ MP4 / MOV / FLV)
without decoding or re-encoding any streams.

Wraps libobs's `media_remux_job_*` API. The remuxer copies elementary
streams (H.264/AV1/AAC/etc. packets) from the source container into the
destination container, rewriting only the timestamps and headers. Result:
identical audio/video quality, but a different file format.

Typical use: a recording app captures to MKV (corruption-safe — recovers
from a crash mid-record) and the user later converts to MP4 for sharing.

Example::

    from pylibobs.remux import MediaRemux

    job = MediaRemux("recording.mkv", "recording.mp4")
    job.run(progress=lambda pct: print(f"{pct*100:.1f}%"))
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from ._ffi import ffi, get_lib


class MediaRemux:
    """A single remux job — wraps `media_remux_job_t`."""

    __slots__ = ("_handle", "_in", "_out", "_progress_cb_keepalive")

    def __init__(self, in_path: str | Path, out_path: str | Path) -> None:
        lib = get_lib()
        self._in  = str(in_path)
        self._out = str(out_path)
        self._progress_cb_keepalive = None

        handle = ffi.new("media_remux_job_t *")
        ok = lib.media_remux_job_create(
            handle, self._in.encode(), self._out.encode(),
        )
        if not ok or handle[0] == ffi.NULL:
            raise RuntimeError(
                f"media_remux_job_create failed for {self._in!r} → {self._out!r}. "
                "Check that the input file exists and the output container is "
                "supported (MP4 / MKV / FLV / MOV)."
            )
        self._handle = handle[0]

    @classmethod
    def can_remux(cls, in_path: str | Path, out_path: str | Path) -> bool:
        """Probe whether libobs can remux this pair without actually doing
        any work. Returns False if creation fails."""
        try:
            job = cls(in_path, out_path)
        except RuntimeError:
            return False
        job.release()
        return True

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def run(
        self,
        progress: Callable[[float], bool | None] | None = None,
    ) -> bool:
        """Process the remux job synchronously. Returns True on success.

        `progress(percent)` is called periodically with a float in [0.0, 1.0].
        Return False from the callback to cancel; True (or None) to continue.
        """
        lib = get_lib()
        if self._handle == ffi.NULL:
            raise RuntimeError("Remux job has already been released")

        cb_ptr = ffi.NULL
        if progress is not None:
            @ffi.callback("bool(void *, float)")
            def _trampoline(_data, percent):
                try:
                    result = progress(float(percent))
                    # libobs interprets True as "continue", False as "cancel".
                    return bool(result) if result is not None else True
                except Exception:
                    return True   # swallow & continue

            self._progress_cb_keepalive = _trampoline
            cb_ptr = _trampoline

        ok = lib.media_remux_job_process(self._handle, cb_ptr, ffi.NULL)
        return bool(ok)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def release(self) -> None:
        if self._handle != ffi.NULL:
            try:
                get_lib().media_remux_job_destroy(self._handle)
            except Exception:
                pass
            self._handle = ffi.NULL
        self._progress_cb_keepalive = None

    def __del__(self) -> None:
        try: self.release()
        except Exception: pass

    def __enter__(self) -> "MediaRemux":
        return self

    def __exit__(self, *_) -> None:
        self.release()

    def __repr__(self) -> str:
        return f"MediaRemux({self._in!r} → {self._out!r})"


def remux(
    in_path: str | Path,
    out_path: str | Path,
    progress: Callable[[float], bool | None] | None = None,
) -> bool:
    """One-shot helper: create + run + release in a single call."""
    with MediaRemux(in_path, out_path) as job:
        return job.run(progress=progress)
