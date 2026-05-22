"""
Integration tests — require a real libobs installation.

Run with:  pytest -m integration
On Linux CI, prepend:  Xvfb :99 -screen 0 1920x1080x24 & DISPLAY=:99 pytest -m integration
"""

import pytest

pytestmark = pytest.mark.integration


def test_import():
    """Verify that pylibobs imports cleanly."""
    import pylibobs
    assert pylibobs.__version__


def test_libobs_found():
    """Verify that find_libobs() resolves to a real file."""
    from pathlib import Path
    from pylibobs._lib import find_libobs
    path = find_libobs()
    assert Path(path).exists(), f"libobs not found at {path}"


def test_obs_startup_shutdown():
    """Full lifecycle: startup → version check → shutdown."""
    from pylibobs import OBSContext

    with OBSContext(locale="en-US") as obs:
        assert obs.initialized
        assert obs.version  # non-empty version string

    # After __exit__, obs_shutdown was called
    assert not obs.initialized


def test_obs_reset_video():
    from pylibobs import OBSContext

    with OBSContext() as obs:
        obs.set_video(width=1280, height=720, fps_num=30)
        # No exception = success


def test_obs_reset_audio():
    from pylibobs import OBSContext

    with OBSContext() as obs:
        obs.set_audio(samples_per_sec=44100)
        # No exception = success


def test_obs_data_roundtrip():
    """OBSData should survive a string/int/bool roundtrip."""
    from pylibobs import OBSContext, OBSData

    with OBSContext() as obs:
        d = OBSData({"server": "rtmp://example.com", "bitrate": 6000, "enabled": True})
        assert d.get_string("server") == "rtmp://example.com"
        assert d.get_int("bitrate") == 6000
        assert d.get_bool("enabled") is True
