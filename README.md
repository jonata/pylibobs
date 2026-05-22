# pylibobs

Python bindings for **libobs** — the core C library of [OBS Studio](https://obsproject.com/).

Lets Python scripts and apps drive libobs directly: initialize OBS, build scenes, configure
encoders, mix audio, and record / stream — all without OBS Studio's UI running.

> **Status:** beta. The public API is feature-complete and covered by tests. Reference counting
> semantics match OBS 32's `obs_*_get_ref()` model.

---

## Why?

Existing options:

- **`obspython`** runs *inside* OBS only — you can't `pip install` it or use it from a normal Python app.
- **`obsws-python` / `simpleobsws`** talk to OBS via WebSocket — requires OBS to be running, and only
  exposes what the WebSocket API allows.

`pylibobs` links libobs directly (via `cffi`), so **your Python process is the OBS host**.

---

## License

Copyright (C) 2026  Jonata Bolzan Loss and contributors.

pylibobs is licensed under **GPL v2 or later**, inherited from libobs.
See [LICENSE](LICENSE) for the full text.

The published wheels bundle libobs's compiled binaries (also GPLv2+),
so the wheel as distributed is covered by GPLv2+. Anything you build
on top of pylibobs must be GPL-compatible if you redistribute it.
Personal use carries no obligation.

---

## Installation

```bash
pip install pylibobs
```

That's it on Windows / macOS / Linux. The wheel ships with **bundled libobs binaries** (libobs
plus its plugin DLLs and data files, sourced from the official OBS Studio release on PyPI's
build server). You don't need to install OBS Studio.

If you're installing from sdist (rare — only when no wheel is published for your platform), or
you want to use a system-installed OBS, the loader falls back through:

1. `$LIBOBS_PATH` environment variable (explicit override)
2. Bundled libs inside the wheel — `pylibobs/_libs/<platform>/<arch>/`
3. `ctypes.util.find_library("obs")`
4. Well-known OBS Studio install paths

Maintainers / contributors can refresh the bundled libs by running:

```bash
python scripts/fetch_libs.py                  # current platform
python scripts/fetch_libs.py --all            # every platform
python scripts/fetch_libs.py --version 32.1.2 # pin OBS version
```

This downloads libobs from the official OBS GitHub release. The `_libs/` tree is `.gitignore`d
and only populated during wheel builds.

---

## Quick start

```python
import time
from pylibobs import (
    OBSContext, OBSData, Source, Scene, Output,
    VideoEncoder, AudioEncoder,
)

with OBSContext() as obs:
    obs.set_video(width=1920, height=1080, fps_num=60)
    obs.set_audio()
    obs.load_modules()

    scene = Scene.create("main")
    cap = Source.create("monitor_capture", "Desktop", {"monitor": 0})
    scene.add(cap)

    venc = VideoEncoder.create("obs_x264", "video", {"crf": 23, "preset": "veryfast"})
    aenc = AudioEncoder.create("ffmpeg_aac", "audio", {"bitrate": 192})

    out = Output.create("ffmpeg_muxer", "rec", {"path": "out.mkv"})
    out.set_video_encoder(venc)
    out.set_audio_encoder(aenc)
    out.start()

    time.sleep(10)
    out.stop()
```

See `examples/` for full recording and streaming scripts.

### pylibobs-studio (tkinter, stdlib only)

`examples/pylibobs_studio.py` is a complete OBS-style desktop application
built on nothing but the Python standard library:

```bash
python examples/pylibobs_studio.py
```

Features:

| Pane | What it does |
|---|---|
| **Live preview** | libobs's D3D11 renderer draws directly into a tkinter `Frame` via its native HWND (`Frame.winfo_id()` → `Display.from_window(hwnd, w, h)`). No Qt, no GTK, no extra deps. |
| **Scenes** | Add / remove scenes; selecting one routes it to the program output. |
| **Sources** | Per-scene list; add via a type-picker dialog populated from `enum_input_types()`, with auto-launched monitor/window/file pickers for the source types that need them. Reorder, toggle visibility, remove. |
| **Audio mixer** | One row per audio-capable source: live VU meter (green / yellow / red), volume slider on an IEC dB curve, mute toggle. Levels come from a `VolumeMeter` queue read on the tk main loop. |
| **Recording** | Standard MKV recording with live frames / bytes / dropped-frames in the status bar. |

The whole app is ~600 lines in a single file. Use it as a starting point
for your own pylibobs-based applications.

---

## API overview

| Class            | Wraps              | Notes                                        |
|------------------|--------------------|----------------------------------------------|
| `OBSContext`     | `obs_startup` / `obs_shutdown`, video/audio reset | Use as a context manager. |
| `OBSData`        | `obs_data_t`       | Dict-like; `OBSData({"k": "v"})`             |
| `Source`         | `obs_source_t`     | `Source.create(kind, name, settings)`        |
| `Scene` / `SceneItem` | `obs_scene_t` / `obs_sceneitem_t` | Add sources, set visibility, iterate items |
| `VideoEncoder` / `AudioEncoder` | `obs_encoder_t` | Per-type factory                |
| `Service`        | `obs_service_t`    | RTMP/streaming targets                       |
| `Output`         | `obs_output_t`     | File or stream sinks; `start()`/`stop()`     |
| `Display`        | `obs_display_t`    | Live preview into a native window (HWND)     |

---

## Testing

```bash
pip install -e ".[dev]"

# Unit tests (mocked cffi layer — fast, no libobs needed)
pytest tests/unit

# Integration tests (need a real libobs)
pytest tests/integration -m integration

# On Linux CI with no display:
Xvfb :99 -screen 0 1920x1080x24 &
DISPLAY=:99 pytest tests/integration -m integration
```

CI runs the full matrix on Windows, Linux, and macOS — see `.github/workflows/ci.yml`.

---

## Project layout

```
pylibobs/
├── pylibobs/
│   ├── _lib.py            # Library locator
│   ├── _ffi.py            # cffi instance
│   ├── _declarations.py   # C API declarations for cdef()
│   ├── context.py         # OBSContext
│   ├── data.py            # OBSData
│   ├── source.py          # Source
│   ├── scene.py           # Scene / SceneItem
│   ├── encoder.py         # VideoEncoder / AudioEncoder
│   ├── service.py         # Service
│   ├── output.py          # Output
│   └── _libs/             # Bundled libobs binaries (after fetch_libs.py)
├── tests/unit/            # Mocked tests
├── tests/integration/     # Real libobs tests
├── scripts/fetch_libs.py  # Pull libobs from OBS releases
└── examples/              # record_to_file.py, stream_to_rtmp.py
```

---

## Coverage / known gaps

`pylibobs` currently declares **100% of the public libobs API** (all 1388 exported
`obs_*` / `gs_*` / `signal_*` / `audio_resampler_*` / `media_remux_*` functions are callable
via `pylibobs._ffi.get_lib()`). Pythonic class-based wrappers cover the common workflows:

- Lifecycle, video/audio init, scenes, sources, scene items, transforms (pos/scale/rot/crop/bounds)
- Outputs (file + RTMP streaming), encoders (incl. ROI hints), services
- Live preview (`Display` attached to a native window via HWND)
- Filters, transitions, hotkeys, fader + VU meter, audio monitoring
- Raw audio/video callbacks (numpy-friendly), audio resampler, media remux
- Properties API (read + edit, with type-aware widgets in `examples/pylibobs_studio.py`)
- Save / load whole scene collections to JSON

What's intentionally raw-only (callable via `get_lib()` but no class wrapper):

- The 290 `gs_*` graphics primitives — exposing them invites GPU-thread bugs; use
  `obs_render_main_texture()` instead.
- Property *builders* (`obs_properties_add_*`) — only useful for C plugin authors.
- Multi-canvas API (`obs_canvas_*`), `obs_view_*`, codec bitstream parsers
  (`obs_avc_*` / `obs_av1_*`).

---

## Contributing

```bash
git clone https://github.com/jonata/pylibobs.git
cd pylibobs
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python scripts/fetch_libs.py                          # download bundled libobs
pytest                                                # 100+ tests, mock + integration
```

The integration suite needs process isolation (libobs can't gracefully restart inside a
single process); use the included runner:

```bash
python scripts/run_tests.py
```

---

## Release process

1. Bump `version` in `pyproject.toml` and tag the commit `vX.Y.Z`.
2. Push the tag. GitHub Actions:
   - Builds platform-specific wheels with bundled libobs (Windows / Linux / macOS Intel + Apple Silicon)
   - Builds the sdist
   - Publishes to PyPI via [Trusted Publishing](https://docs.pypi.org/trusted-publishers/) (no token needed in repo secrets)
   - Attaches all wheels to a GitHub Release with auto-generated notes

To set up Trusted Publishing on PyPI for this repo, register `pylibobs` as a project on PyPI,
then in *Project settings → Publishing*, add a "GitHub Actions" trusted publisher pointing at
`<owner>/pylibobs` / workflow `release.yml` / environment `pypi`.

---

Contributions welcome — PRs against `main`.
