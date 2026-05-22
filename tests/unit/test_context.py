"""Unit tests for OBSContext lifecycle — cffi layer is mocked."""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest


@pytest.fixture()
def mock_lib():
    lib = MagicMock()
    lib.obs_initialized.return_value = False
    lib.obs_startup.return_value = True
    lib.obs_reset_video.return_value = 0   # OBS_VIDEO_SUCCESS
    lib.obs_reset_audio.return_value = True
    lib.obs_get_version_string.return_value = b"30.0.0"
    return lib


@pytest.fixture()
def ctx(mock_lib, monkeypatch):
    monkeypatch.setattr("pylibobs.context.get_lib", lambda: mock_lib)
    monkeypatch.setattr("pylibobs._ffi.get_lib", lambda: mock_lib)
    ffi_mod = MagicMock()
    ffi_mod.NULL = None
    ffi_mod.new.return_value = MagicMock()
    monkeypatch.setattr("pylibobs.context.ffi", ffi_mod)
    from pylibobs.context import OBSContext
    return OBSContext(locale="en-US"), mock_lib, ffi_mod


def test_startup_calls_obs_startup(ctx):
    obs, lib, ffi_mod = ctx
    obs.startup()
    lib.obs_startup.assert_called_once()
    args = lib.obs_startup.call_args[0]
    assert args[0] == b"en-US"


def test_startup_skips_if_already_initialized(ctx):
    obs, lib, _ = ctx
    lib.obs_initialized.return_value = True
    obs.startup()
    lib.obs_startup.assert_not_called()


def test_startup_raises_on_failure(ctx):
    obs, lib, _ = ctx
    lib.obs_startup.return_value = False
    with pytest.raises(RuntimeError, match="obs_startup"):
        obs.startup()


def test_shutdown_calls_obs_shutdown(ctx):
    obs, lib, _ = ctx
    obs._started = True  # pretend startup ran
    obs.shutdown()
    lib.obs_shutdown.assert_called_once()
    assert obs._started is False


def test_shutdown_is_noop_when_not_started(ctx):
    obs, lib, _ = ctx
    obs.shutdown()  # _started is False by default
    lib.obs_shutdown.assert_not_called()


def test_context_manager_calls_startup_shutdown(ctx):
    obs, lib, _ = ctx
    with obs:
        lib.obs_startup.assert_called_once()
    lib.obs_shutdown.assert_called_once()


def test_set_video_calls_obs_reset_video(ctx):
    obs, lib, ffi_mod = ctx
    obs.set_video(width=1920, height=1080, fps_num=30)
    lib.obs_reset_video.assert_called_once()


def test_set_video_raises_on_failure(ctx):
    obs, lib, _ = ctx
    lib.obs_reset_video.return_value = -2   # OBS_VIDEO_INVALID_PARAM
    with pytest.raises(RuntimeError, match="obs_reset_video"):
        obs.set_video()


def test_set_audio_calls_obs_reset_audio(ctx):
    obs, lib, ffi_mod = ctx
    obs.set_audio(samples_per_sec=48000)
    lib.obs_reset_audio.assert_called_once()


def test_set_audio_raises_on_failure(ctx):
    obs, lib, _ = ctx
    lib.obs_reset_audio.return_value = False
    with pytest.raises(RuntimeError, match="obs_reset_audio"):
        obs.set_audio()
