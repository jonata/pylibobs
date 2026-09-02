"""Offscreen render + CPU readback of an obs source into BGRA.

``render_source_to_bgra`` composites any source (a scene, a single source, a
transition …) into an off-screen texture and stages it back to CPU memory as
BGRA bytes — the building block for a thumbnail/preview that must leave the GPU.
It enters the graphics context itself (``obs_enter_graphics``), so it is safe to
call from a worker thread while the main render loop runs; the graphics mutex
serialises the two.

Unlike ``add_raw_video_callback``/``obs_view``, this renders a *specific* source
on demand, independent of the program (main) mix.
"""

from __future__ import annotations

from ._ffi import ffi, get_lib

# gs_color_format.GS_BGRA / gs_zstencil_format.GS_ZS_NONE / gs_clear_flags.
_GS_BGRA = 5
_GS_ZS_NONE = 0
_GS_CLEAR_COLOR = 1


def render_source_to_bgra(
    source,
    width: int,
    height: int,
    *,
    canvas_width: int = 0,
    canvas_height: int = 0,
) -> tuple[bytes, int] | None:
    """Render ``source`` off-screen and return ``(bgra_bytes, stride)`` or ``None``.

    The source is composited into a ``width`` x ``height`` BGRA texture and read
    back to CPU memory. ``canvas_width`` / ``canvas_height`` give the coordinate
    space the source composes in (default: ``width`` / ``height`` for a 1:1
    render); pass the obs base-canvas size to scale a full-canvas scene into a
    smaller target. ``stride`` (bytes per row) may exceed ``width * 4`` — honour
    it when reading the buffer. Returns ``None`` if the source is NULL, the
    dimensions are invalid, or any graphics step fails.
    """
    lib = get_lib()
    ptr = getattr(source, "_ptr", source)
    if not ptr or ptr == ffi.NULL:
        return None
    w, h = int(width), int(height)
    if w <= 0 or h <= 0:
        return None
    canvas_w = int(canvas_width) or w
    canvas_h = int(canvas_height) or h

    lib.obs_enter_graphics()
    texrender = ffi.NULL
    stage = ffi.NULL
    try:
        texrender = lib.gs_texrender_create(_GS_BGRA, _GS_ZS_NONE)
        stage = lib.gs_stagesurface_create(w, h, _GS_BGRA)
        if texrender == ffi.NULL or stage == ffi.NULL:
            return None
        lib.gs_texrender_reset(texrender)
        if not lib.gs_texrender_begin(texrender, w, h):
            return None
        try:
            clear = ffi.new("struct vec4 *")
            clear.x = clear.y = clear.z = 0.0
            clear.w = 1.0  # opaque black background
            lib.gs_clear(_GS_CLEAR_COLOR, clear, 0.0, 0)
            lib.gs_ortho(0.0, float(canvas_w), 0.0, float(canvas_h), -100.0, 100.0)
            lib.obs_source_video_render(ptr)
        finally:
            lib.gs_texrender_end(texrender)
        lib.gs_stage_texture(stage, lib.gs_texrender_get_texture(texrender))
        data_pp = ffi.new("uint8_t **")
        linesize_p = ffi.new("uint32_t *")
        if not lib.gs_stagesurface_map(stage, data_pp, linesize_p):
            return None
        try:
            stride = int(linesize_p[0])
            data = bytes(ffi.buffer(data_pp[0], stride * h))
        finally:
            lib.gs_stagesurface_unmap(stage)
        return data, stride
    finally:
        if stage != ffi.NULL:
            lib.gs_stagesurface_destroy(stage)
        if texrender != ffi.NULL:
            lib.gs_texrender_destroy(texrender)
        lib.obs_leave_graphics()
