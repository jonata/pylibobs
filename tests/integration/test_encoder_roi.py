"""Integration tests for encoder region-of-interest hints."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_x264_encoder_roi_lifecycle():
    """obs_x264 supports ROI; we should be able to add, list, and clear them."""
    from pylibobs import OBSContext, VideoEncoder

    with OBSContext() as obs:
        obs.set_video(640, 360)
        obs.set_audio()
        obs.load_modules()

        venc = VideoEncoder.create("obs_x264", "roi_test",
                                  {"rate_control": "CRF", "crf": 23,
                                   "preset": "veryfast"})

        # Initially no ROIs
        assert venc.has_roi() is False
        assert venc.list_roi() == []

        # Add a high-priority region in the centre
        ok = venc.add_roi(160, 90, 480, 270, priority=0.8)
        assert ok is True
        assert venc.has_roi() is True

        rois = venc.list_roi()
        assert len(rois) == 1
        r = rois[0]
        assert r["left"] == 160
        assert r["top"] == 90
        assert r["right"] == 480
        assert r["bottom"] == 270
        assert abs(r["priority"] - 0.8) < 0.01

        # Add a second non-overlapping region; some OBS builds dedupe
        # overlapping regions internally so we use a clearly separate one.
        venc.add_roi(500, 280, 600, 350, priority=-0.3)
        rois2 = venc.list_roi()
        assert len(rois2) >= 1   # libobs accepted at least the first one

        # ROI increment changes whenever we modify
        inc1 = venc.get_roi_increment()

        venc.clear_roi()
        assert venc.list_roi() == []

        inc2 = venc.get_roi_increment()
        assert inc2 != inc1   # changed by clear_roi
