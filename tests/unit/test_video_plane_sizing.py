"""Unit tests for raw-video plane byte sizing (no libobs needed).

Sizing every plane at the full frame height over-reads the chroma planes of
4:2:0 formats (NV12/I420 hold only height/2 rows) — an out-of-bounds read past
the frame allocation. :func:`_plane_row_count` must halve those.
"""

from __future__ import annotations

from pylibobs.callbacks import _plane_row_count


def test_nv12_chroma_plane_is_half_height():
    assert _plane_row_count(2, 0, 720) == 720   # Y
    assert _plane_row_count(2, 1, 720) == 360   # interleaved UV


def test_i420_chroma_planes_are_half_height():
    assert _plane_row_count(1, 0, 480) == 480
    assert _plane_row_count(1, 1, 480) == 240
    assert _plane_row_count(1, 2, 480) == 240


def test_full_height_chroma_formats():
    # I444 (full-res) and I422 (horizontal-only subsampling) keep full height.
    assert _plane_row_count(10, 1, 100) == 100
    assert _plane_row_count(12, 1, 100) == 100


def test_packed_formats_use_full_height():
    assert _plane_row_count(7, 0, 200) == 200   # BGRA
    assert _plane_row_count(4, 0, 200) == 200   # YUY2 (packed 4:2:2)


def test_unknown_plane_index_defaults_to_full_height():
    # A plane past the format's known planes falls back to the safe full height.
    assert _plane_row_count(2, 5, 128) == 128
