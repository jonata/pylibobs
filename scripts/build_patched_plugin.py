#!/usr/bin/env python3
"""
Build the bundled obs-ffmpeg plugin from patched OBS sources.

The binaries fetched by fetch_libs.py come from official OBS releases, so they
carry stock behaviour. Any change we want in the bundle has to be compiled from
source against the SAME OBS tag fetch_libs.py pins: libobs refuses to load a
module whose `obs_module_ver` disagrees with `obs_get_version`.

Right now the only patch is `patches/preserve-audio-pitch.patch`, which makes
the Media Source keep audio pitch when its speed is not 100%. It touches
shared/media-playback/, which is compiled into the obs-ffmpeg plugin, so
rebuilding that one plugin is enough — libobs and every other plugin stay as
downloaded.

    python scripts/fetch_libs.py --platform linux --arch x86_64  # first
    python scripts/build_patched_plugin.py                       # then this

The rebuilt plugin replaces:
    pylibobs/_libs/linux/x86_64/obs-plugins/obs-ffmpeg.so

Build requirements (Ubuntu 24.04):
    sudo apt install build-essential cmake ninja-build git pkg-config \
        libavcodec-dev libavdevice-dev libavfilter-dev libavformat-dev \
        libavutil-dev libswresample-dev libswscale-dev libcurl4-openssl-dev \
        libjansson-dev libpulse-dev libx11-dev libx11-xcb-dev libxcb1-dev \
        libxcb-randr0-dev libxcb-shm0-dev libxcb-xfixes0-dev libxcb-xinerama0-dev \
        libxcomposite-dev libxinerama-dev libgl1-mesa-dev libwayland-dev \
        libpipewire-0.3-dev libdrm-dev libva-dev libv4l-dev libudev-dev \
        libasound2-dev libfdk-aac-dev libfontconfig-dev libfreetype-dev \
        libjack-jackd2-dev libluajit-5.1-dev libpci-dev librist-dev libsrt-openssl-dev \
        libspeexdsp-dev libssl-dev libuuid1 uuid-dev libxkbcommon-dev \
        libsimde-dev uthash-dev nlohmann-json3-dev libqrcodegencpp-dev \
        extra-cmake-modules qt6-base-dev libx264-dev patchelf

(qt6-base-dev and libx264-dev are needed because OBS's CMake configures the
frontend-tools and obs-x264 plugins even when they are not built.)

Only Linux x86_64 is supported for now: the Windows and macOS wheels keep the
stock plugin, so they keep stock behaviour.
"""

from __future__ import annotations

import argparse
import ctypes
import platform
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PATCH = REPO_ROOT / "patches" / "preserve-audio-pitch.patch"
LIBS_DIR = REPO_ROOT / "pylibobs" / "_libs"
OBS_REPO = "https://github.com/obsproject/obs-studio.git"

#: Plugin target to rebuild, and the ids it registers. A rebuild that drops one
#: of these would silently cost pylibobs a source, an output or an encoder, so
#: they are checked before the plugin is installed. Ids the downloaded plugin
#: doesn't have either (an OBS version may add or drop one) are not required.
PLUGIN = "obs-ffmpeg"
PLUGIN_IDS = (
    "ffmpeg_source",         # media source — what this patch is about
    "ffmpeg_output",
    "ffmpeg_muxer",
    "ffmpeg_hls_muxer",
    "ffmpeg_mpegts_muxer",   # needs librist/libsrt at build time
    "ffmpeg_aac",
    "ffmpeg_opus",
    "ffmpeg_alac",
    "ffmpeg_flac",
)

#: Everything not needed for obs-ffmpeg is switched off: the Qt frontend, the
#: browser/websocket submodules and the plugins that pull extra SDKs. SRT/RIST
#: (ENABLE_NEW_MPEGTS_OUTPUT) and VA-API stay on, because the official builds
#: ship them inside obs-ffmpeg and dropping them would be a regression.
CMAKE_OPTIONS = [
    "-DCMAKE_BUILD_TYPE=RelWithDebInfo",
    "-DENABLE_FRONTEND=OFF",
    "-DENABLE_BROWSER=OFF",
    "-DENABLE_WEBSOCKET=OFF",
    "-DENABLE_WEBRTC=OFF",
    "-DENABLE_AJA=OFF",
    "-DENABLE_DECKLINK=OFF",
    "-DENABLE_SCRIPTING=OFF",
    "-DENABLE_VST=OFF",
    "-DENABLE_VLC=OFF",
    "-DENABLE_QSV11=OFF",
    "-DENABLE_NVENC=OFF",
]


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print("  $", " ".join(str(c) for c in cmd))
    subprocess.run(cmd, cwd=cwd, check=True)


def obs_tag() -> str:
    """The tag fetch_libs.py pins, so the plugin matches the bundled libobs."""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from fetch_libs import DEFAULT_OBS_TAG

    return DEFAULT_OBS_TAG


def checkout_sources(src: Path, tag: str) -> None:
    if (src / ".git").exists():
        print(f"Using existing source tree: {src}")
        return
    print(f"Cloning obs-studio {tag} into {src} ...")
    src.parent.mkdir(parents=True, exist_ok=True)
    run(["git", "clone", "--depth", "1", "--branch", tag, "--recurse-submodules",
         "--shallow-submodules", OBS_REPO, str(src)])


def apply_patch(src: Path) -> None:
    already = subprocess.run(["git", "apply", "--reverse", "--check", str(PATCH)],
                             cwd=src, capture_output=True).returncode == 0
    if already:
        print("Patch already applied.")
        return
    print(f"Applying {PATCH.name} ...")
    run(["git", "apply", str(PATCH)], cwd=src)


def build(src: Path, jobs: int | None, simde_include: str | None) -> Path:
    options = list(CMAKE_OPTIONS)
    if simde_include:
        options.append(f"-DSIMDe_INCLUDE_DIR={simde_include}")
    run(["cmake", "-S", str(src), "-B", str(src / "build"), "-G", "Ninja", *options])
    ninja = ["ninja", "-C", str(src / "build"), PLUGIN]
    if jobs:
        ninja += ["-j", str(jobs)]
    run(ninja)
    built = src / "build" / "plugins" / PLUGIN / f"{PLUGIN}.so"
    if not built.exists():
        sys.exit(f"Build produced no {built}")
    return built


def _ids(plugin: Path) -> set[str]:
    out = subprocess.run(["strings", str(plugin)], capture_output=True, text=True).stdout
    return {line for line in out.splitlines() if line in PLUGIN_IDS}


def _semver(ver: int) -> str:
    return f"{ver >> 24}.{(ver >> 16) & 0xFF}.{ver & 0xFFFF}"


def verify(plugin: Path, tag: str, stock: Path | None, bundled_libobs: Path) -> None:
    """Check the module matches the BUNDLED libobs and still registers everything."""
    # libobs first and globally: the plugin resolves its symbols against it, so
    # this compares the built module with the libobs that will actually load it
    # — not merely with the tag we asked to build.
    obs = ctypes.CDLL(str(bundled_libobs), mode=ctypes.RTLD_GLOBAL)
    obs.obs_get_version.restype = ctypes.c_uint32
    bundled_ver = obs.obs_get_version()

    try:
        lib = ctypes.CDLL(str(plugin), mode=ctypes.RTLD_LOCAL)
    except OSError as exc:
        sys.exit(f"Built plugin cannot be loaded against the bundled libobs: {exc}")
    lib.obs_module_ver.restype = ctypes.c_uint32
    ver = lib.obs_module_ver()
    got = _semver(ver)
    if ver != bundled_ver:
        sys.exit(f"Built plugin reports OBS {got}, but the bundled libobs is "
                 f"{_semver(bundled_ver)} — libobs would refuse to load it. Either re-run "
                 f"'python scripts/fetch_libs.py --version {got}', or build '--tag {_semver(bundled_ver)}'.")
    if got != tag:
        sys.exit(f"Built plugin reports OBS {got}, but this run asked for {tag} — "
                 "stale source tree? Remove it, or pass --src-dir.")

    built_ids = _ids(plugin)
    # Only require what the downloaded plugin provides, so a future OBS release
    # that drops an encoder doesn't fail the build for no reason.
    wanted = _ids(stock) if stock and stock.is_file() else set(PLUGIN_IDS)
    missing = sorted(wanted - built_ids)
    if missing:
        sys.exit(f"Built plugin is missing: {', '.join(missing)}. "
                 "A build dependency is probably absent (librist/libsrt for mpegts, libva for VA-API).")
    print(f"Verified: obs_module_ver {got}, registers {len(built_ids)} ids including ffmpeg_source")


def install(built: Path, plat: str, arch: str) -> Path:
    dest_dir = LIBS_DIR / plat / arch / "obs-plugins"
    if not dest_dir.is_dir():
        sys.exit(f"{dest_dir} not found — run scripts/fetch_libs.py first.")
    dest = dest_dir / built.name
    stock = dest.with_suffix(".so.stock")
    if dest.exists() and not stock.exists():
        shutil.copy2(dest, stock)
        print(f"Kept the downloaded plugin as {stock.name}")
    shutil.copy2(built, dest)
    # CMake bakes the build tree into DT_RUNPATH, and its trailing empty entry
    # makes ld.so search the current directory for every library the plugin
    # needs. The downloaded plugin has no RUNPATH; the rebuilt one must not
    # either, or a published wheel would search the builder's paths first.
    run(["patchelf", "--remove-rpath", str(dest)])
    left = subprocess.run(["patchelf", "--print-rpath", str(dest)],
                          capture_output=True, text=True).stdout.strip()
    if left:
        sys.exit(f"RUNPATH survived on {dest}: {left}")
    if shutil.which("strip"):
        run(["strip", "--strip-unneeded", str(dest)])
    return dest


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tag", default=None, help="OBS tag to build (default: the pin in fetch_libs.py)")
    ap.add_argument("--src-dir", default=None, help="where to clone/build OBS (default: build/obs-<tag>)")
    ap.add_argument("--jobs", type=int, default=None, help="parallel build jobs")
    ap.add_argument("--simde-include", default=None,
                    help="directory containing simde/, if libsimde-dev is not installed")
    args = ap.parse_args()

    if sys.platform != "linux" or platform.machine() != "x86_64":
        sys.exit("Only linux/x86_64 is supported; other platforms keep the stock plugin.")
    for tool in ("git", "cmake", "ninja", "pkg-config", "patchelf"):
        if not shutil.which(tool):
            sys.exit(f"'{tool}' not found — see the build requirements in this script's docstring.")
    if not PATCH.is_file():
        sys.exit(f"Patch not found: {PATCH}")

    # Check what we install into before spending a clone and a build on it.
    plugins_dir = LIBS_DIR / "linux" / "x86_64" / "obs-plugins"
    downloaded = plugins_dir / f"{PLUGIN}.so"
    bundled_libobs = LIBS_DIR / "linux" / "x86_64" / "libobs.so.0"
    if not downloaded.is_file() or not bundled_libobs.is_file():
        sys.exit("No bundled libobs found — run "
                 "'python scripts/fetch_libs.py --platform linux --arch x86_64' first.")

    tag = args.tag or obs_tag()
    src = Path(args.src_dir) if args.src_dir else REPO_ROOT / "build" / f"obs-{tag}"

    print(f"Building {PLUGIN} from obs-studio {tag}")
    checkout_sources(src, tag)
    apply_patch(src)
    built = build(src, args.jobs, args.simde_include)
    stock = plugins_dir / f"{PLUGIN}.so.stock"
    verify(built, tag, stock if stock.is_file() else downloaded, bundled_libobs)
    dest = install(built, "linux", "x86_64")
    print(f"\nInstalled {dest} ({dest.stat().st_size // 1024} KB)")
    print("The bundled Media Source now keeps audio pitch at any playback speed.")


if __name__ == "__main__":
    main()
