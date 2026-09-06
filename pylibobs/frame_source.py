"""An async video source you push frames into, registered from pure Python.

libobs has no built-in "here are some pixels" source: displaying frames produced by the
application (a rendered overlay, an off-screen browser, a decoded still) normally means
shipping a C plugin that registers an ``OBS_SOURCE_ASYNC_VIDEO`` type. That is awkward for
pylibobs, which bundles prebuilt libobs binaries and compiles nothing.

This registers such a source through ``obs_register_source_s`` using cffi callbacks, so no
compiler or plugin DLL is involved:

    import pylibobs
    pylibobs.register_frame_source()
    src = pylibobs.Source.create(pylibobs.FRAME_SOURCE_ID, "my-content", {})
    pylibobs.push_video_frame(src, bgra_bytes, 1920, 1080)

Notes
-----
* ``obs_register_source_s`` takes an explicit struct size, which is libobs' ABI-versioning
  path: it copies only that many bytes and zeroes the rest. Only the leading fields are
  declared here, so this stays correct across libobs versions that append fields.
* ``OBS_SOURCE_ASYNC`` is ``1 << 2``. (``1 << 8`` is ``OBS_SOURCE_DEPRECATED`` — using it
  registers a *synchronous* source, which then demands ``get_width``/``get_height`` and
  never displays pushed frames.) For a true async source libobs takes the size from the
  frame, so no size callbacks are needed.
* A source only ticks while it is in the active tree — assign it to a scene or an output
  channel, or pushed frames will queue and never be promoted.
"""

from __future__ import annotations

import threading
from typing import Any

from ._ffi import ffi, get_lib

FRAME_SOURCE_ID = "pylibobs_frame_source"

OBS_SOURCE_TYPE_INPUT = 0
OBS_SOURCE_VIDEO = 1 << 0
OBS_SOURCE_ASYNC = 1 << 2
OBS_SOURCE_ASYNC_VIDEO = OBS_SOURCE_ASYNC | OBS_SOURCE_VIDEO

_VIDEO_FORMAT_BGRA = 7

_lock = threading.Lock()
_registered: dict[str, Any] = {}


def _head_ffi():
    """A private FFI declaring only the leading fields of struct obs_source_info."""
    import cffi

    f = cffi.FFI()
    f.cdef("""
        typedef struct obs_data   obs_data_t;
        typedef struct obs_source obs_source_t;
        struct obs_source_info_head {
            const char *id;
            int   type;
            uint32_t output_flags;
            const char *(*get_name)(void *type_data);
            void *(*create)(obs_data_t *settings, obs_source_t *source);
            void  (*destroy)(void *data);
        };
    """)
    return f


def register_frame_source(
    source_id: str = FRAME_SOURCE_ID,
    display_name: str | None = None,
) -> bool:
    """Register an async video source that displays frames pushed into it.

    Idempotent: registering the same ``source_id`` twice is a no-op. Returns ``True`` if the
    source id is available for :meth:`Source.create` afterwards.

    Must be called after the OBS context is started and before creating the source.
    """
    with _lock:
        if source_id in _registered:
            return True
        if source_id in enum_source_types():
            # Already provided by a loaded plugin — registering again would make
            # libobs log a duplicate-id error and change nothing.
            return True

        lib = get_lib()
        head = _head_ffi()

        name_c = head.new("char[]", source_id.encode("utf-8"))
        label_c = head.new("char[]", (display_name or source_id).encode("utf-8"))
        # libobs treats a NULL return from create() as failure, so hand back any non-NULL
        # pointer; this source keeps no per-instance state.
        instance_c = head.new("char[]", b"\0")

        @head.callback("const char *(void *)")
        def _get_name(_type_data):
            return label_c

        @head.callback("void *(obs_data_t *, obs_source_t *)")
        def _create(_settings, _source):
            return instance_c

        @head.callback("void (void *)")
        def _destroy(_data):
            return

        info = head.new("struct obs_source_info_head *")
        info.id = name_c
        info.type = OBS_SOURCE_TYPE_INPUT
        info.output_flags = OBS_SOURCE_ASYNC_VIDEO
        info.get_name = _get_name
        info.create = _create
        info.destroy = _destroy

        lib.obs_register_source_s(
            ffi.cast("struct obs_source_info *", int(head.cast("uintptr_t", info))),
            head.sizeof("struct obs_source_info_head"),
        )

        # Everything above must outlive registration — libobs keeps the pointers.
        _registered[source_id] = (head, info, name_c, label_c, instance_c,
                                  _get_name, _create, _destroy)

    return source_id in enum_source_types()


def enum_source_types() -> list[str]:
    """Every source id libobs currently knows."""
    lib = get_lib()
    out: list[str] = []
    index = 0
    while True:
        holder = ffi.new("const char **")
        if not lib.obs_enum_source_types(index, holder):
            return out
        out.append(ffi.string(holder[0]).decode("utf-8", "replace"))
        index += 1


def push_video_frame(
    source: Any,
    data: bytes,
    width: int,
    height: int,
    *,
    stride: int | None = None,
    video_format: int = _VIDEO_FORMAT_BGRA,
    timestamp_ns: int | None = None,
) -> None:
    """Push one frame into a source created from :func:`register_frame_source`.

    ``data`` is ``height * stride`` bytes (``stride`` defaults to ``width * 4``, i.e. BGRA).
    libobs copies the frame, so ``data`` need not outlive the call. Frames are promoted on
    the next tick — the source must be in the active tree to be ticked.
    """
    if width <= 0 or height <= 0 or not data:
        return
    row = stride if stride is not None else width * 4
    lib = get_lib()

    frame = ffi.new("struct obs_source_frame *")
    buf = ffi.from_buffer(data)
    frame.data[0] = ffi.cast("uint8_t *", buf)
    frame.linesize[0] = row
    frame.width = width
    frame.height = height
    frame.format = video_format
    frame.full_range = True
    frame.timestamp = timestamp_ns if timestamp_ns is not None else _monotonic_ns()
    lib.obs_source_output_video(source._ptr, frame)


def _monotonic_ns() -> int:
    import time

    return time.monotonic_ns()


__all__ = [
    "FRAME_SOURCE_ID",
    "OBS_SOURCE_ASYNC_VIDEO",
    "register_frame_source",
    "push_video_frame",
    "enum_source_types",
]
