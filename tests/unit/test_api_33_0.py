"""
Unit tests for the libobs 33.0 update: declarations, the core-module layout
of system installs, and the fetcher's flattening of that layout. No libobs
needed.
"""

from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path
from unittest.mock import patch

from pylibobs import _declarations, _declarations_auto
from pylibobs._lib import QT_FRONTEND_MODULES, get_system_core_modules

ROOT = Path(__file__).resolve().parents[2]


def _real_declarations() -> str:
    """Every cdef string pylibobs feeds cffi, minus the void(void) stubs."""
    parts = [v for k, v in vars(_declarations).items() if k.isupper() and isinstance(v, str)]
    parts.append(_declarations_auto.AUTO_DECLS)
    return "\n".join(parts)


def _declared_signature(name: str) -> str | None:
    m = re.search(rf"^[^\n/]*\b{name}\s*\([^;]*\);", _real_declarations(), re.M)
    return m.group(0).strip() if m else None


def test_monitoring_switch_is_declared():
    assert _declared_signature("obs_source_set_monitoring_enabled") == \
        "void obs_source_set_monitoring_enabled(obs_source_t *source, bool enabled);"
    assert _declared_signature("obs_source_get_monitoring_enabled") == \
        "bool obs_source_get_monitoring_enabled(const obs_source_t *source);"


def test_functions_removed_in_33_are_not_declared():
    """libobs 33 no longer exports these; declaring them would hand out names
    that fail only when called."""
    for name in ("obs_add_core_module", "gs_image_file_init", "gs_image_file_free",
                 "gs_image_file2_init", "gs_image_file3_init", "gs_image_file4_init"):
        assert _declared_signature(name) is None, f"{name} is still declared"


def test_find_modules_takes_a_real_callback():
    """load_modules() passes a cffi callback to obs_find_modules, which needs the
    curated typedef, not the generator's opaque `struct ..._s *` placeholder."""
    from pylibobs._ffi import ffi
    assert ffi.typeof("obs_find_module_callback_t").cname == \
        "void(*)(void *, struct obs_module_info *)"
    assert "obs_find_module_callback_s" not in _declarations_auto.PREAMBLE


def test_no_typedefs_from_vendored_libnsgif():
    """libnsgif's function-pointer members made the generator emit typedefs
    named after their parameters; `width` would then clash with struct fields."""
    for bogus in ("create", "width", "x0", "display"):
        assert not re.search(rf"\*\s*{bogus};", _declarations_auto.PREAMBLE), bogus


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    return path


def test_system_core_modules_linux_layout(tmp_path):
    lib_dir = tmp_path / "usr/local/lib/x86_64-linux-gnu"
    libobs = _touch(lib_dir / "libobs.so.0")
    for name in ("obs-ffmpeg", "obs-x264", "frontend-tools", "libcef"):
        _touch(lib_dir / "obs-modules/core" / f"{name}.so")
    data = tmp_path / "usr/local/share/obs/obs-modules/core"
    data.mkdir(parents=True)

    with patch("pylibobs._lib.find_libobs", return_value=str(libobs)), \
         patch("pylibobs._lib.platform.system", return_value="Linux"):
        modules = get_system_core_modules()

    assert modules == [
        ("obs-ffmpeg", str(lib_dir / "obs-modules/core/obs-ffmpeg.so"), str(data / "obs-ffmpeg")),
        ("obs-x264", str(lib_dir / "obs-modules/core/obs-x264.so"), str(data / "obs-x264")),
    ]


def test_system_core_modules_windows_layout(tmp_path):
    libobs = _touch(tmp_path / "obs-studio/bin/64bit/obs.dll")
    core = tmp_path / "obs-studio/core"
    for name in ("win-capture", "obs-websocket"):
        _touch(core / name / f"{name}.dll")
    (core / "not-a-module").mkdir()

    with patch("pylibobs._lib.find_libobs", return_value=str(libobs)), \
         patch("pylibobs._lib.platform.system", return_value="Windows"):
        modules = get_system_core_modules()

    assert modules == [("win-capture", str(core / "win-capture/win-capture.dll"),
                        str(core / "win-capture/data"))]


def test_system_core_modules_empty_for_pre_33_layout(tmp_path):
    libobs = _touch(tmp_path / "lib/libobs.so.0")
    _touch(tmp_path / "lib/obs-plugins/obs-ffmpeg.so")
    with patch("pylibobs._lib.find_libobs", return_value=str(libobs)), \
         patch("pylibobs._lib.platform.system", return_value="Linux"):
        assert get_system_core_modules() == []


def test_qt_frontend_modules_cover_the_known_aborters():
    assert {"frontend-tools", "decklink-output-ui"} <= QT_FRONTEND_MODULES


def _fetch_libs():
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import fetch_libs
    finally:
        sys.path.pop(0)
    return fetch_libs


def test_zip_modules_flatten_onto_obs_plugins(tmp_path):
    fetch_libs = _fetch_libs()
    archive = tmp_path / "obs.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("core/win-dshow/win-dshow.dll", "dll")
        zf.writestr("core/win-dshow/data/obs-virtualcam-module64.dll", "vcam")
        zf.writestr("core/obs-browser/libcef.dll", "cef")
        zf.writestr("bin/64bit/obs.dll", "obs")

    dst = tmp_path / "out"
    assert fetch_libs._extract_zip_modules(archive, "core/", dst) == 3
    assert (dst / "obs-plugins/win-dshow.dll").read_text() == "dll"
    assert (dst / "obs-plugins/libcef.dll").exists()
    assert (dst / "data/obs-plugins/win-dshow/obs-virtualcam-module64.dll").exists()
    assert not (dst / "obs.dll").exists()


def test_moves_rename_and_prune(tmp_path):
    fetch_libs = _fetch_libs()
    _touch(tmp_path / "obs-modules/core/obs-x264.so")
    _touch(tmp_path / "data/obs-modules/core/obs-x264/locale/en-US.ini")
    fetch_libs._apply_moves(tmp_path, {
        "obs-modules/core": "obs-plugins",
        "data/obs-modules/core": "data/obs-plugins",
    })
    assert (tmp_path / "obs-plugins/obs-x264.so").exists()
    assert (tmp_path / "data/obs-plugins/obs-x264/locale/en-US.ini").exists()
    assert not (tmp_path / "obs-modules").exists()
    assert not (tmp_path / "data/obs-modules").exists()
