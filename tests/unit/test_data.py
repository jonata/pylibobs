"""Unit tests for OBSData — cffi layer is mocked."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures — mock the cffi lib before importing OBSData
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_lib(monkeypatch):
    lib = MagicMock()
    # obs_data_create returns a fake non-NULL pointer
    fake_ptr = MagicMock()
    fake_ptr.__eq__ = lambda self, other: False  # ptr != ffi.NULL
    lib.obs_data_create.return_value = fake_ptr

    ffi_mod = MagicMock()
    ffi_mod.NULL = None

    monkeypatch.setattr("pylibobs._ffi.get_lib", lambda: lib)
    monkeypatch.setattr("pylibobs._ffi.ffi", ffi_mod)
    monkeypatch.setattr("pylibobs.data.ffi", ffi_mod)
    monkeypatch.setattr("pylibobs.data.get_lib", lambda: lib)

    return lib, ffi_mod, fake_ptr


def _make_data(mock_lib):
    lib, ffi_mod, fake_ptr = mock_lib
    from pylibobs.data import OBSData
    d = OBSData.__new__(OBSData)
    d._ptr = fake_ptr
    d._owned = True
    return d, lib, ffi_mod


def test_set_string(mock_lib):
    d, lib, ffi_mod = _make_data(mock_lib)
    d["url"] = "rtmp://live.twitch.tv/app"
    lib.obs_data_set_string.assert_called_once_with(
        d._ptr, b"url", b"rtmp://live.twitch.tv/app"
    )


def test_set_int(mock_lib):
    d, lib, _ = _make_data(mock_lib)
    d["bitrate"] = 6000
    lib.obs_data_set_int.assert_called_once_with(d._ptr, b"bitrate", 6000)


def test_set_float(mock_lib):
    d, lib, _ = _make_data(mock_lib)
    d["scale"] = 1.5
    lib.obs_data_set_double.assert_called_once_with(d._ptr, b"scale", 1.5)


def test_set_bool_true(mock_lib):
    d, lib, _ = _make_data(mock_lib)
    d["enabled"] = True
    lib.obs_data_set_bool.assert_called_once_with(d._ptr, b"enabled", True)


def test_bool_before_int(mock_lib):
    """bool is a subclass of int — must dispatch to set_bool, not set_int."""
    d, lib, _ = _make_data(mock_lib)
    d["flag"] = True
    lib.obs_data_set_bool.assert_called_once()
    lib.obs_data_set_int.assert_not_called()


def test_set_unsupported_type_raises(mock_lib):
    d, lib, _ = _make_data(mock_lib)
    with pytest.raises(TypeError, match="Cannot store"):
        d["bad"] = [1, 2, 3]


def test_delete_calls_erase(mock_lib):
    d, lib, _ = _make_data(mock_lib)
    del d["key"]
    lib.obs_data_erase.assert_called_once_with(d._ptr, b"key")


def test_release_called_on_del(mock_lib):
    d, lib, ffi_mod = _make_data(mock_lib)
    d._owned = True
    ptr = d._ptr  # capture BEFORE release zeroes it
    d.__del__()
    lib.obs_data_release.assert_called_once_with(ptr)
    assert d._ptr == ffi_mod.NULL
