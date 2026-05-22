"""
Platform-aware libobs shared library locator.

Resolution order:
  1. LIBOBS_PATH environment variable (override for development)
  2. Bundled lib in pylibobs/_libs/<platform>/<arch>/
  3. ctypes.util.find_library("obs")
  4. Well-known OBS Studio install paths
"""
from __future__ import annotations    # lazy-evaluated annotations (Py3.9 compat)

import os
import platform
from pathlib import Path

_PACKAGE_DIR = Path(__file__).parent
_LIBS_DIR = _PACKAGE_DIR / "_libs"

_PLATFORM_LIB_NAMES = {
    "Windows": "obs.dll",
    "Linux": "libobs.so.0",
    "Darwin": "libobs.dylib",
}

_PLATFORM_SUBDIR = {
    "Windows": "windows",
    "Linux": "linux",
    "Darwin": "macos",
}

_ARCH_ALIASES = {
    "amd64": "x86_64",
    "x86_64": "x86_64",
    "arm64": "arm64",
    "aarch64": "arm64",
}

_SYSTEM_FALLBACK_PATHS = {
    "Windows": [
        r"C:\Program Files\obs-studio\bin\64bit\obs.dll",
        r"C:\Program Files (x86)\obs-studio\bin\64bit\obs.dll",
    ],
    "Linux": [
        "/usr/lib/x86_64-linux-gnu/libobs.so.0",
        "/usr/lib/aarch64-linux-gnu/libobs.so.0",
        "/usr/lib/libobs.so.0",
        "/usr/local/lib/libobs.so.0",
    ],
    "Darwin": [
        "/Applications/OBS.app/Contents/Frameworks/libobs.0.dylib",
        "/usr/local/lib/libobs.dylib",
        "/opt/homebrew/lib/libobs.dylib",
    ],
}


def _env_override() -> str | None:
    return os.environ.get("LIBOBS_PATH") or None


def _bundled_path() -> str | None:
    """Locate the bundled libobs shared library inside the wheel.

    Layout per platform:
      windows/<arch>/obs.dll            (alongside zlib, w32-pthreads, etc.)
      linux/<arch>/libobs.so.0          (plus obs-plugins/ and data/ siblings)
      macos/<arch>/Frameworks/libobs.dylib
                              (@rpath deps live alongside it in Frameworks/)
    """
    system = platform.system()
    machine = platform.machine().lower()
    arch = _ARCH_ALIASES.get(machine, machine)
    subdir = _PLATFORM_SUBDIR.get(system)
    lib_name = _PLATFORM_LIB_NAMES.get(system)
    if not subdir or not lib_name:
        return None

    base = _LIBS_DIR / subdir / arch
    # Try the most-likely path first per platform
    candidates = [
        base / lib_name,                          # win/linux flat layout
        base / "Frameworks" / lib_name,           # macOS .app layout
        base / "Frameworks" / "libobs.0.dylib",   # macOS versioned alias
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return None


def _system_path() -> str | None:
    from ctypes.util import find_library

    system = platform.system()
    name = find_library("obs")
    if name:
        p = Path(name)
        if p.exists():
            return str(p)

    for path in _SYSTEM_FALLBACK_PATHS.get(system, []):
        if Path(path).exists():
            return path
    return None


def find_libobs() -> str:
    """Return the path to the libobs shared library, or raise ImportError."""
    path = _env_override() or _bundled_path() or _system_path()
    if not path:
        system = platform.system()
        msg = (
            "libobs shared library not found.\n\n"
            "Options:\n"
            "  1. Install OBS Studio: https://obsproject.com/download\n"
            "  2. Bundle libobs: python scripts/fetch_libs.py\n"
            f"  3. Set LIBOBS_PATH to the full path of the library "
            f"({_PLATFORM_LIB_NAMES.get(system, 'libobs shared lib')})\n"
        )
        raise ImportError(msg)
    return path


# OBS helpers that libobs spawns via GetModuleFileNameA(NULL)/<helper>.exe —
# they must sit next to the host EXE (python.exe), not next to obs.dll.
_OBS_HELPER_EXES_WINDOWS = [
    "obs-ffmpeg-mux.exe",   # ffmpeg_muxer output (recording)
    "obs-amf-test.exe",     # AMD encoder probe
    "obs-nvenc-test.exe",   # NVENC probe
    "obs-qsv-test.exe",     # QuickSync probe
]


def _get_host_module_dir() -> Path | None:
    """
    Return the directory of the actual host module on Windows.

    libobs uses GetModuleFileNameW(NULL) to locate helper exes. In a venv,
    this returns the BASE python.exe (e.g. C:\\Python312\\python.exe), not
    the venv launcher. So we must stage helpers there.
    """
    if platform.system() != "Windows":
        return None
    import ctypes
    from ctypes import wintypes

    GetModuleFileNameW = ctypes.windll.kernel32.GetModuleFileNameW
    GetModuleFileNameW.argtypes = [wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
    GetModuleFileNameW.restype = wintypes.DWORD
    buf = ctypes.create_unicode_buffer(1024)
    n = GetModuleFileNameW(None, buf, 1024)
    if n == 0:
        return None
    return Path(buf.value).parent


def _stage_helpers_next_to_host(lib_dir: Path) -> None:
    """Copy OBS helper EXEs to the directory of the actual host EXE."""
    if platform.system() != "Windows":
        return
    import shutil

    host_dir = _get_host_module_dir()
    if host_dir is None:
        return

    for name in _OBS_HELPER_EXES_WINDOWS:
        src = lib_dir / name
        if not src.exists():
            continue
        dst = host_dir / name
        try:
            if dst.exists() and dst.stat().st_size == src.stat().st_size:
                continue  # already staged
            shutil.copy2(src, dst)
        except (PermissionError, OSError):
            pass  # best-effort; user may not have write access


def prepare_dll_search_path(libobs_path: str) -> None:
    """
    On Windows, libobs.dll has many dependency DLLs in the same folder.
    Add that folder to the DLL search path so they can be resolved.

    Also stages OBS helper executables next to sys.executable, since libobs
    locates them via GetModuleFileNameA(NULL).

    No-op on Linux/macOS (those use rpath / standard ld search).
    """
    if platform.system() != "Windows":
        return

    lib_dir = Path(libobs_path).parent
    lib_dir_str = str(lib_dir)

    if hasattr(os, "add_dll_directory"):
        try:
            os.add_dll_directory(lib_dir_str)
        except (FileNotFoundError, OSError):
            pass

    cur = os.environ.get("PATH", "")
    if lib_dir_str not in cur.split(os.pathsep):
        os.environ["PATH"] = lib_dir_str + os.pathsep + cur

    _stage_helpers_next_to_host(lib_dir)


def get_obs_data_dir() -> str | None:
    """
    Return the OBS data directory (containing libobs/ shader effects),
    or None if not found.

    Resolution order:
      1. OBS_DATA_PATH env var
      2. Bundled `_libs/<plat>/<arch>/data` (if present)
      3. Bundled `_libs/<plat>/<arch>/../../data` (legacy layout)
      4. OS-standard OBS install paths
    """
    env = os.environ.get("OBS_DATA_PATH")
    if env and Path(env).exists():
        return env

    try:
        libobs_path = Path(find_libobs())
    except ImportError:
        return None

    # Co-located bundled data (same directory as the DLL)
    for candidate in [
        libobs_path.parent / "data",
        libobs_path.parent.parent.parent / "data",  # OBS install layout
    ]:
        if candidate.exists():
            return str(candidate)

    system = platform.system()
    if system == "Windows":
        candidates = [
            Path(r"C:\Program Files\obs-studio\data"),
        ]
    elif system == "Linux":
        candidates = [Path("/usr/share/obs"), Path("/usr/local/share/obs")]
    elif system == "Darwin":
        candidates = [Path("/Applications/OBS.app/Contents/Resources/data")]
    else:
        candidates = []

    for c in candidates:
        if c.exists():
            return str(c)
    return None


def get_obs_module_dirs() -> tuple[str, str]:
    """
    Return (plugin_bin_dir, plugin_data_dir) for obs_add_module_path.

    Tries the bundled layout first (pylibobs/_libs/.../obs-plugins/), then
    falls back to the OS-standard OBS Studio install layout.
    """
    system = platform.system()
    libobs_path = Path(find_libobs()).resolve()
    lib_dir = libobs_path.parent

    # 1. Bundled layout (fetch_libs.py extracts plugins next to obs.dll)
    bundled_plugins = lib_dir / "obs-plugins"
    bundled_data = lib_dir / "data" / "obs-plugins" / "%module%"
    if bundled_plugins.exists():
        return str(bundled_plugins), str(bundled_data)

    # 2. OS-standard OBS install layout
    if system == "Windows":
        obs_root = lib_dir.parent.parent  # bin/64bit/.. -> install root
        return (
            str(obs_root / "obs-plugins" / "64bit"),
            str(obs_root / "data" / "obs-plugins" / "%module%"),
        )

    elif system == "Linux":
        for bin_dir, data_dir in [
            ("/usr/lib/x86_64-linux-gnu/obs-plugins", "/usr/share/obs/obs-plugins/%module%"),
            ("/usr/lib/obs-plugins", "/usr/share/obs/obs-plugins/%module%"),
            ("/usr/local/lib/obs-plugins", "/usr/local/share/obs/obs-plugins/%module%"),
        ]:
            if Path(bin_dir).exists():
                return bin_dir, data_dir
        return "/usr/lib/obs-plugins", "/usr/share/obs/obs-plugins/%module%"

    elif system == "Darwin":
        if "OBS.app" in str(lib_dir):
            app_contents = lib_dir
            while app_contents.name != "Contents" and app_contents != app_contents.parent:
                app_contents = app_contents.parent
            return (
                str(app_contents / "Resources" / "obs-plugins"),
                str(app_contents / "Resources" / "data" / "obs-plugins" / "%module%"),
            )
        return "/usr/local/lib/obs-plugins", "/usr/local/share/obs/obs-plugins/%module%"

    return "", ""
