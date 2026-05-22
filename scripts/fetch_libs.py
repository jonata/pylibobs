#!/usr/bin/env python3
"""
Download bundled libobs binaries from official OBS Studio GitHub releases.

This script is called during wheel building (see .github/workflows/release.yml)
and may also be run by maintainers locally:

    python scripts/fetch_libs.py                       # current platform
    python scripts/fetch_libs.py --all                 # every platform
    python scripts/fetch_libs.py --platform linux --arch x86_64
    python scripts/fetch_libs.py --version 32.1.2      # pin OBS version

The bundled files are written under:
    pylibobs/_libs/<platform>/<arch>/

The `_libs/` tree is intentionally NOT committed to git — it's downloaded
fresh by CI for each release.

Requirements:  `pip install requests`
"""

from __future__ import annotations

import argparse
import hashlib
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("Install 'requests' first:  pip install requests")

REPO       = "obsproject/obs-studio"
GITHUB_API = f"https://api.github.com/repos/{REPO}/releases"
LIBS_DIR   = Path(__file__).parent.parent / "pylibobs" / "_libs"

# --------------------------------------------------------------------------
# Asset patterns per (platform, arch). Each entry tells us:
#   - asset_re:      regex matching the GitHub release asset filename
#   - kind:          "zip" / "deb" / "dmg"
#   - extract:       what to pull out (see _extract for the schema)
# --------------------------------------------------------------------------
ASSET_PATTERNS: dict[tuple[str, str], dict] = {
    ("windows", "x86_64"): {
        "asset_re": r"OBS-Studio-[\d.]+-Windows-x64\.zip$",
        "kind": "zip",
        # Self-contained: extract bin/, data/, obs-plugins/
        "extract": {
            "bin/64bit/":         "",            # → _libs/.../
            "data/":              "data/",
            "obs-plugins/64bit/": "obs-plugins/",
        },
        "verify_file": "obs.dll",
    },
    ("windows", "arm64"): {
        "asset_re": r"OBS-Studio-[\d.]+-Windows-arm64\.zip$",
        "kind": "zip",
        "extract": {
            "bin/64bit/":         "",
            "data/":              "data/",
            "obs-plugins/64bit/": "obs-plugins/",
        },
        "verify_file": "obs.dll",
    },
    ("linux", "x86_64"): {
        # OBS's Ubuntu .deb installs under /usr/local/ (CMake's default
        # CMAKE_INSTALL_PREFIX), not /usr/. Layout:
        #   usr/local/lib/x86_64-linux-gnu/libobs.so.0
        #   usr/local/lib/x86_64-linux-gnu/obs-plugins/*.so
        #   usr/local/share/obs/libobs/*.effect        (shader effects)
        #   usr/local/share/obs/obs-plugins/*/         (plugin data)
        "asset_re": r"OBS-Studio-[\d.]+-Ubuntu-[\d.]+-x86_64\.deb$",
        "kind": "deb",
        "extract": {
            "usr/local/lib/x86_64-linux-gnu/":  "",
            "usr/local/share/obs/":             "data/",
        },
        "verify_file": "libobs.so.0",
    },
    ("macos", "x86_64"): {
        "asset_re": r"OBS-Studio-[\d.]+-macOS-Intel\.dmg$",
        "kind": "dmg",
        "verify_file": "Frameworks/libobs.dylib",
    },
    ("macos", "arm64"): {
        "asset_re": r"OBS-Studio-[\d.]+-macOS-Apple\.dmg$",
        "kind": "dmg",
        "verify_file": "Frameworks/libobs.dylib",
    },
}


# ==========================================================================
# GitHub release lookup
# ==========================================================================
def get_release(version: str | None = None) -> dict:
    if version:
        url = f"{GITHUB_API}/tags/{version}"
        print(f"Fetching release {version}...")
    else:
        url = f"{GITHUB_API}/latest"
        print("Fetching latest OBS release...")
    headers = {"Accept": "application/vnd.github+json"}
    # Optional auth — works around GitHub's anonymous 60-req/hr limit on CI
    import os
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    r = requests.get(url, timeout=30, headers=headers)
    r.raise_for_status()
    return r.json()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path) -> None:
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  cached: {dest.name}")
        return
    print(f"  downloading {url} ...")
    with requests.get(url, stream=True, timeout=300) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        done  = 0
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                f.write(chunk)
                done += len(chunk)
                if total:
                    pct = done * 100 // total
                    sys.stdout.write(f"\r  {pct:3d}%")
                    sys.stdout.flush()
    print()


# ==========================================================================
# Extractors
# ==========================================================================
def _extract_zip_tree(zip_path: Path, src_prefix: str, dst: Path) -> int:
    dst.mkdir(parents=True, exist_ok=True)
    n = 0
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            if not name.startswith(src_prefix) or name.endswith("/"):
                continue
            rel = name[len(src_prefix):]
            if not rel:
                continue
            out = dst / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(name) as src, open(out, "wb") as out_fh:
                shutil.copyfileobj(src, out_fh)
            n += 1
    return n


def _extract_deb_tree(deb_path: Path, src_prefix: str, dst: Path) -> int:
    """Extract files under `src_prefix` from a .deb into `dst`.

    Strategy:
      1. If `dpkg-deb` is available (always on Debian/Ubuntu), use it —
         it handles every data.tar.{xz,gz,zst} format correctly.
      2. Otherwise fall back to a hand-rolled ar+tar parser.
    """
    if shutil.which("dpkg-deb"):
        return _extract_deb_tree_dpkg(deb_path, src_prefix, dst)
    return _extract_deb_tree_python(deb_path, src_prefix, dst)


def _extract_deb_tree_dpkg(deb_path: Path, src_prefix: str, dst: Path) -> int:
    """Use the system `dpkg-deb` tool — most reliable."""
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.check_call(["dpkg-deb", "-x", str(deb_path), tmp])
        src_root = Path(tmp) / src_prefix.rstrip("/")
        if not src_root.exists():
            print(f"  [!] '{src_prefix}' not found in {deb_path.name}")
            return 0
        dst.mkdir(parents=True, exist_ok=True)
        n = 0
        for src in src_root.rglob("*"):
            if not src.is_file():
                continue
            rel = src.relative_to(src_root)
            out = dst / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, out)
            n += 1
        return n


def _extract_deb_tree_python(deb_path: Path, src_prefix: str, dst: Path) -> int:
    """Hand-rolled .deb extractor — used when dpkg-deb isn't available.
    A .deb is an `ar` archive containing data.tar.{xz,gz,zst}."""
    import io
    import tarfile

    with open(deb_path, "rb") as f:
        magic = f.read(8)
        if magic != b"!<arch>\n":
            raise RuntimeError(f"Not a valid .deb: {deb_path}")

        data_blob = None
        data_name = None
        while True:
            header = f.read(60)
            if len(header) < 60:
                break
            name = header[:16].decode("ascii", errors="replace").rstrip(" /\x00")
            size = int(header[48:58].decode("ascii", errors="replace").strip())
            payload = f.read(size)
            if size % 2:
                f.read(1)
            if name.startswith("data.tar"):
                data_blob = payload
                data_name = name
                break

    if not data_blob:
        raise RuntimeError(f"data.tar.* not found in {deb_path}")

    if data_name.endswith(".zst"):
        try:
            import zstandard as zstd
        except ImportError:
            sys.exit("Install 'zstandard' for .deb extraction:  pip install zstandard")
        bio = io.BytesIO(zstd.ZstdDecompressor().decompress(data_blob))
        mode = "r:"
    else:
        bio = io.BytesIO(data_blob)
        mode = "r:*"

    n = 0
    dst.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=bio, mode=mode) as tf:
        for member in tf.getmembers():
            name = member.name.lstrip("./")
            if not name.startswith(src_prefix):
                continue
            rel = name[len(src_prefix):]
            if not rel or member.isdir():
                continue
            out = dst / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            ex = tf.extractfile(member)
            if ex is None:
                continue
            with open(out, "wb") as out_fh:
                shutil.copyfileobj(ex, out_fh)
            n += 1
    return n


def _extract_dmg(dmg_path: Path, dst_root: Path) -> int:
    """Mount the DMG with `hdiutil`, copy the .app's Frameworks + Resources
    over, then unmount. macOS-only.

    OBS on macOS packages libobs as a .framework bundle (Mach-O convention),
    not a flat .dylib. After extraction we surface the binary at
    `Frameworks/libobs.dylib` (a copy/symlink) so the rest of the build —
    including the wheel's verify check — finds it without knowing about
    framework internals.
    """
    if sys.platform != "darwin":
        print("  [!] DMG extraction requires macOS (uses hdiutil). Skipping.")
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        mount_pt = Path(tmp) / "mnt"
        mount_pt.mkdir()
        subprocess.check_call(
            ["hdiutil", "attach", str(dmg_path), "-mountpoint", str(mount_pt),
             "-nobrowse", "-quiet"],
        )
        try:
            # OBS's .dmg sometimes contains "OBS.app", sometimes "OBS Studio.app".
            apps = list(mount_pt.glob("*.app"))
            if not apps:
                # Diagnostic: dump the mount contents so the failure is obvious
                print("  [!] No .app bundle found in DMG. Mount contents:")
                for p in mount_pt.iterdir():
                    print(f"      {p.name}")
                raise RuntimeError("No .app bundle inside DMG")
            app = apps[0]
            print(f"    found app: {app.name}")
            contents = app / "Contents"

            if (contents / "Frameworks").exists():
                shutil.copytree(contents / "Frameworks",
                                dst_root / "Frameworks",
                                dirs_exist_ok=True, symlinks=True)
            if (contents / "Resources").exists():
                shutil.copytree(contents / "Resources",
                                dst_root / "data",
                                dirs_exist_ok=True, symlinks=True)

            # Locate the libobs binary wherever the .app put it. Common
            # layouts:
            #   Frameworks/libobs.dylib                            (flat)
            #   Frameworks/libobs.0.dylib                          (versioned)
            #   Frameworks/libobs.framework/Versions/A/libobs       (framework)
            #   Frameworks/libobs.framework/libobs                  (legacy)
            frameworks_dir = dst_root / "Frameworks"
            real_libobs = None
            for cand in [
                frameworks_dir / "libobs.dylib",
                frameworks_dir / "libobs.0.dylib",
                frameworks_dir / "libobs.framework" / "Versions" / "A" / "libobs",
                frameworks_dir / "libobs.framework" / "libobs",
            ]:
                if cand.exists():
                    real_libobs = cand
                    break

            if real_libobs is None:
                # Last-ditch: any file named "libobs*" anywhere in Frameworks
                for cand in frameworks_dir.rglob("libobs*"):
                    if cand.is_file() and not cand.is_symlink():
                        real_libobs = cand
                        break

            if real_libobs is None:
                print(f"  [!] No libobs binary found in {frameworks_dir}. Layout:")
                for p in sorted(frameworks_dir.rglob("*"))[:30]:
                    print(f"      {p.relative_to(dst_root)}")
                raise RuntimeError("libobs binary not located inside .app/Frameworks")
            print(f"    libobs at: {real_libobs.relative_to(dst_root)}")

            # Standard top-level alias so _lib.py and verify_file find it.
            top = frameworks_dir / "libobs.dylib"
            if real_libobs != top:
                if top.exists() or top.is_symlink():
                    top.unlink()
                shutil.copy2(real_libobs, top)
            return sum(1 for _ in dst_root.rglob("*") if _.is_file())
        finally:
            subprocess.call(["hdiutil", "detach", str(mount_pt), "-quiet"])


# ==========================================================================
# Per-platform entry point
# ==========================================================================
def fetch_for(plat: str, arch: str, release: dict, cache: Path) -> bool:
    key = (plat, arch)
    cfg = ASSET_PATTERNS.get(key)
    if cfg is None:
        print(f"  unsupported platform: {plat}/{arch}")
        return False

    # Find the matching release asset
    pattern = re.compile(cfg["asset_re"])
    assets = release.get("assets", [])
    asset  = next((a for a in assets if pattern.search(a["name"])), None)
    if asset is None:
        print(f"  [!] no matching asset for {cfg['asset_re']!r}")
        print(f"      available: {[a['name'] for a in assets]}")
        return False

    print(f"  asset: {asset['name']}")
    archive = cache / asset["name"]
    download(asset["browser_download_url"], archive)

    dst = LIBS_DIR / plat / arch
    # Clean slate
    if dst.exists():
        shutil.rmtree(dst)

    kind = cfg["kind"]
    total = 0
    if kind == "zip":
        for src_prefix, sub in cfg["extract"].items():
            n = _extract_zip_tree(archive, src_prefix, dst / sub)
            print(f"    +{n} files from {src_prefix} -> {sub or '.'}")
            total += n
    elif kind == "deb":
        for src_prefix, sub in cfg["extract"].items():
            n = _extract_deb_tree(archive, src_prefix, dst / sub)
            print(f"    +{n} files from {src_prefix} -> {sub or '.'}")
            total += n
    elif kind == "dmg":
        total = _extract_dmg(archive, dst)
    else:
        print(f"  unsupported kind: {kind}")
        return False

    verify = cfg.get("verify_file")
    if verify and not (dst / verify).exists():
        print(f"  [!] expected {verify} missing after extraction")
        return False

    print(f"  OK: {total} files in {dst}")
    return True


# ==========================================================================
# CLI
# ==========================================================================
def _current_platform() -> tuple[str, str]:
    sys_name = sys.platform
    if sys_name.startswith("linux"):
        plat = "linux"
    elif sys_name == "darwin":
        plat = "macos"
    elif sys_name == "win32":
        plat = "windows"
    else:
        plat = sys_name

    machine = platform.machine().lower()
    arch = {"amd64": "x86_64", "x86_64": "x86_64",
            "arm64": "arm64", "aarch64": "arm64"}.get(machine, machine)
    return plat, arch


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true",
                    help="Fetch for every supported platform")
    ap.add_argument("--platform", default=None,
                    help="Override platform (windows / linux / macos)")
    ap.add_argument("--arch", default=None,
                    help="Override arch (x86_64 / arm64)")
    ap.add_argument("--version", default=None,
                    help="OBS Studio version tag, e.g. 32.1.2")
    args = ap.parse_args()

    release = get_release(args.version)
    print(f"Using OBS release: {release.get('tag_name', '?')}\n")

    cache = Path(__file__).parent / ".fetch_cache"
    cache.mkdir(exist_ok=True)

    if args.all:
        targets = list(ASSET_PATTERNS.keys())
    else:
        plat = args.platform or _current_platform()[0]
        arch = args.arch     or _current_platform()[1]
        targets = [(plat, arch)]

    fails = []
    for plat, arch in targets:
        print(f"--- {plat}/{arch} ---")
        if not fetch_for(plat, arch, release, cache):
            fails.append(f"{plat}/{arch}")

    print()
    if fails:
        print(f"Failed: {', '.join(fails)}")
        return 1
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
