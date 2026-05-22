"""
Regression tests for libobs struct layouts.

A field-order mismatch between our cffi declaration and libobs's actual
struct is silent and catastrophic — it doesn't crash, it just writes
each value into the wrong slot. We caught this once when output_format
worked but gpu_conversion / colorspace / scale_type / adapter were all
shifted by one (see git history around the OBS 32 update).

These tests pin the layout we currently target.
"""

from __future__ import annotations

import pytest

from pylibobs._ffi import ffi


def test_obs_video_info_size():
    """OBS 32.x: struct obs_video_info should be 56 bytes on 64-bit.

    Layout (with natural alignment, 8-byte ptr, 4-byte int/enum):
      const char * graphics_module   8
      uint32_t fps_num               4
      uint32_t fps_den               4
      uint32_t base_width            4
      uint32_t base_height           4
      uint32_t output_width          4
      uint32_t output_height         4
      enum video_format output_format 4
      uint32_t adapter               4
      bool gpu_conversion            1 + 3 pad
      enum video_colorspace          4
      enum video_range_type          4
      enum obs_scale_type            4
      ------------------------------ 56
    """
    assert ffi.sizeof("struct obs_video_info") == 56


def test_obs_video_info_field_offsets():
    """Pin the offset of each field — catches accidental reordering."""
    expected = {
        "graphics_module": 0,
        "fps_num":         8,
        "fps_den":         12,
        "base_width":      16,
        "base_height":     20,
        "output_width":    24,
        "output_height":   28,
        "output_format":   32,
        "adapter":         36,
        "gpu_conversion":  40,
        # bool + 3 pad → next field at +4
        "colorspace":      44,
        "range":           48,
        "scale_type":      52,
    }
    typ = ffi.typeof("struct obs_video_info")
    actual = {name: field.offset for name, field in typ.fields}
    assert actual == expected, (
        f"struct obs_video_info field layout drifted!\n"
        f"Expected: {expected}\nGot:      {actual}"
    )


def test_obs_audio_info_size():
    """struct obs_audio_info = uint32_t + enum = 8 bytes."""
    assert ffi.sizeof("struct obs_audio_info") == 8


def test_vec2_size():
    """vec2 is 2 floats."""
    assert ffi.sizeof("struct vec2") == 8


def test_obs_video_info_can_be_written_via_field_names():
    """Smoke test that ffi.new + field assignment actually works on the struct."""
    ovi = ffi.new("struct obs_video_info *")
    ovi.fps_num = 60
    ovi.fps_den = 1
    ovi.base_width = 1920
    ovi.base_height = 1080
    ovi.adapter = 0
    ovi.gpu_conversion = True

    assert ovi.fps_num == 60
    assert ovi.base_width == 1920
    assert ovi.adapter == 0
    assert ovi.gpu_conversion is True
