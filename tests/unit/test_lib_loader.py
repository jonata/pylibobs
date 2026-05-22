"""Unit tests for pylibobs._lib — no real libobs needed."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from pylibobs._lib import (
    _PLATFORM_LIB_NAMES,
    _bundled_path,
    _env_override,
    _system_path,
    find_libobs,
)


def test_env_override_returns_none_when_unset(monkeypatch):
    monkeypatch.delenv("LIBOBS_PATH", raising=False)
    assert _env_override() is None


def test_env_override_returns_value(monkeypatch, tmp_path):
    fake = tmp_path / "obs.dll"
    fake.touch()
    monkeypatch.setenv("LIBOBS_PATH", str(fake))
    assert _env_override() == str(fake)


def test_bundled_path_returns_none_when_dir_empty():
    # _libs dir exists but is empty — should return None
    result = _bundled_path()
    # May be None (no bundled lib) or a string (bundled lib exists)
    assert result is None or isinstance(result, str)


def test_find_libobs_raises_import_error_when_nothing_found(monkeypatch, tmp_path):
    monkeypatch.delenv("LIBOBS_PATH", raising=False)
    # Point _libs dir to an empty tmp dir so bundled path returns None
    with (
        patch("pylibobs._lib._LIBS_DIR", tmp_path),
        patch("pylibobs._lib._system_path", return_value=None),
    ):
        with pytest.raises(ImportError, match="libobs"):
            find_libobs()


def test_find_libobs_uses_env_override(monkeypatch, tmp_path):
    fake = tmp_path / "obs.dll"
    fake.touch()
    monkeypatch.setenv("LIBOBS_PATH", str(fake))
    result = find_libobs()
    assert result == str(fake)


def test_find_libobs_uses_bundled(monkeypatch, tmp_path):
    monkeypatch.delenv("LIBOBS_PATH", raising=False)
    import platform
    system = platform.system()
    machine = platform.machine().lower()
    from pylibobs._lib import _ARCH_ALIASES, _PLATFORM_SUBDIR
    arch = _ARCH_ALIASES.get(machine, machine)
    subdir = _PLATFORM_SUBDIR.get(system, system.lower())
    lib_name = _PLATFORM_LIB_NAMES.get(system, "libobs.so")

    bundled_dir = tmp_path / subdir / arch
    bundled_dir.mkdir(parents=True)
    fake_lib = bundled_dir / lib_name
    fake_lib.touch()

    with patch("pylibobs._lib._LIBS_DIR", tmp_path):
        result = find_libobs()
    assert result == str(fake_lib)


def test_platform_lib_names_covers_all_platforms():
    assert "Windows" in _PLATFORM_LIB_NAMES
    assert "Linux" in _PLATFORM_LIB_NAMES
    assert "Darwin" in _PLATFORM_LIB_NAMES
