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

**Linux:** pylibobs 33 bundles OBS 33's official Linux build, which OBS publishes for Ubuntu
26.04 only. The wheel needs **glibc 2.43+** and the system FFmpeg 8 / x264 libraries of that
generation (Ubuntu 26.04 or newer, or an equally recent distribution). On older systems pip
cannot use the wheel; install the last release for OBS 32 instead:

```bash
pip install "pylibobs<33"
```

Without that pin, pip falls back to building pylibobs 33 from source there, and stops with an
error pointing to this command: the source package carries no libobs. To use pylibobs 33 with a
system-installed OBS 33 instead, set `PYLIBOBS_ALLOW_SYSTEM_LIBOBS=1` when installing.

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
python scripts/fetch_libs.py --version 33.0.0 # pin OBS version
```

This downloads libobs from the official OBS GitHub release. The `_libs/` tree is `.gitignore`d
and only populated during wheel builds.

### macOS runtime

The wheel preserves `libobs.framework` so Cocoa can find its shader resources.
The native dependency graph is relocated and ad-hoc signed when bundled; no
`DYLD_*` overrides or running OBS Studio application are needed. The wheel's
minimum macOS version comes from the official application's `Info.plist`.
Both Intel (`--arch x86_64`) and Apple Silicon (`--arch arm64`) DMGs are supported
by `scripts/fetch_libs.py`, which must run on macOS with Xcode command line tools.
Downloads and cached assets are checked against GitHub's official SHA256 digest;
`runtime.json` records the release, asset digest and minimum OS version.

Capture modules include AVFoundation and ScreenCaptureKit. Permission requests
and Cocoa event dispatch remain the host application's responsibility. Modules
that require OBS Studio's frontend (including its macOS virtual camera module),
Qt, CEF or Syphon are excluded from the headless runtime.

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
| `Display`        | `obs_display_t`    | Live preview into an HWND, X11 window, or Cocoa NSView |

### Native displays

`Display.from_window(handle, width, height)` borrows the native target; release
the display before destroying the window/view and before shutting down libobs.
The graphics-thread draw callback can render any source, scene, or transition
using `pylibobs.display.render_source_letterboxed`.

On macOS, `handle` must point to an `NSView` in the **same process** as libobs.
Create and explicitly release the display on the native main thread, keep the
Cocoa event loop running, and keep the view alive and attached until release.
Supply backing pixels (use the view's `convertRectToBacking:`), and call
`resize()` when its size or Retina scale changes. An NSWindow pointer, window
number, or view pointer received from another process is not a valid target.
The binding has no GUI toolkit dependency; the Cocoa integration test uses
PyObjC solely to create its test window.

---

### macOS camera sinks

`pylibobs.macos_camera.CameraOutput(device_uid)` sends the initialized main video
mix to an existing CoreMediaIO output stream. The device's vendor installs and
enables its camera extension; the binding installs no camera and loads no
frontend plugin. The sink must support dynamically described limited-range
Rec.709 NV12 frames. Its native device UID is configuration supplied by the host.

Use the output as a context manager or call `close()` before OBS shutdown.
`frames_published`, `frames_consumed`, `frames_dropped`, and `last_error` expose
delivery progress. Consumption means the camera service accepted a frame; it
does not imply a conferencing application is capturing. A bounded pixel-buffer
pool and the native stream queue discard excess production without reusing
buffers still owned by downstream consumers. Frame bytes stay in native code.

Use one producer for each destination. CoreMediaIO extensions control access;
extensions that allow competing writers cannot provide exclusive delivery.

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

The camera-source pixel test requires macOS, an enabled idle camera extension,
and `PYLIBOBS_TEST_CAMERA_UID` identifying its NV12-capable sink. It uses a
separate CoreMediaIO reader to verify authored color changes through the actual
camera source, including recovery after abrupt producer termination.

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

## Moving from pylibobs 32 (OBS 32) to 33

- **Audio monitoring is on/off.** OBS 33 replaced the three monitoring types with
  `obs_source_set/get_monitoring_enabled` (the old calls are deprecated). Use
  `Source.monitoring_enabled`. *Monitor only* (heard, but kept out of recordings and streams)
  is now monitoring plus mute: `Source.set_monitor_only()`.
- **Old scene collections:** a source saved with *monitor only* loads in OBS 33 as monitored
  **and** in the output — its audio now reaches recordings and streams. Mute those sources (or
  call `set_monitor_only()`) after loading if that matters.
- **Plugins moved** to `obs-modules/core/` (Linux), `core/<module>/` (Windows) and
  `PlugIns/*.plugin` (macOS). pylibobs finds them in all of these and in the 32.x layouts;
  `OBSContext.failed_modules` lists any module that would not load.
- **Images:** the `gs_image_file`/`2`/`3`/`4` functions are gone; raw callers use
  `gs_image_file_ex_*` (`ffi.new("gs_image_file_ex_t *")`).
- `obs_add_core_module` was removed; `obs_source_set_hidden` / `is_hidden` and
  `obs_load_all_modules` are deprecated (the latter does nothing any more).

## Coverage / known gaps

### macOS surface delivery

`pylibobs.macos_surfaces.SurfacePresenter(nsview)` presents in a borrowed,
same-process `NSView`. Create, poll and close it on the Cocoa main thread,
closing it before destroying the parent view. The presenter does not initialize
libobs and has no GUI toolkit dependency. Give its random `endpoint` to a
`SurfaceProducer(endpoint, width, height)` in the process running libobs.

Call `producer.render(source, canvas_width=..., canvas_height=...)` from the
render loop and `presenter.poll()` from the consumer's event loop. Scenes and
transitions are ordinary sources; `None` explicitly presents opaque black.
The source is borrowed for the entire render call, including graphics-lock waits
and `before_render`. Keep its native owner alive and synchronize release with
the render loop. If the callback invalidates the source, it must veto rendering.
The binding transfers IOSurface rights through Mach messages, never foreign
view pointers or Python frame buffers. Three in-flight buffers bound memory;
a busy consumer drops new frames and polling keeps the newest available frame.
The exported image uses top-left orientation and is letterboxed by the presenter.

Remove owned render callbacks and close the producer before shutting down OBS.
Replacing a producer changes its dimensions; replacing a presenter gives it a
fresh endpoint. OpenGL writes and reads finish before buffer handoff/reuse.
This avoids CPU pixel readback but includes GPU synchronization; software
renderers can still be slow. The macOS wheel ships the small native helper this
needs. Source installs compile it with clang and skip it, with a warning, when
the Xcode command line tools are missing; `macos_surfaces` then raises `OSError`.
`presenter.last_frame_latency_ms` measures the last frame from render entry to
GPU presentation completion using the shared monotonic clock; it excludes scanout.

The endpoint is a name in the user's login session, not a private channel: any
process running as the same user that learns it can connect and show its own
frames in the view. The presenter checks every message (size, format, rights),
so such a process can only show wrong pixels, but don't log the endpoint or
display it, and pass it to the producer over a channel only your processes can
read, such as a pipe.

Run `examples/macos_surface_smoke.py` to validate two-process pixels, resizing,
backpressure and timing. It requires PyObjC only for the example's native window.

### API declarations

`pylibobs` targets **libobs 33.0.0** and declares every function it exports (1381
`obs_*` / `gs_*` / `signal_*` / `proc_*` / `calldata_*` / `audio_output_*` / `video_output_*`
symbols), reachable via `pylibobs._ffi.get_lib()`. 1155 of them carry their full C
signature; the remaining 226 are declared as `void f(void)` placeholders because
`scripts/generate_cdef.py` cannot parse their headers yet — they resolve, but need a
curated signature in `_declarations.py` before they can be called correctly.
Pythonic class-based wrappers cover the common workflows:

- Lifecycle, video/audio init, scenes, sources, scene items, transforms (pos/scale/rot/crop/bounds)
- Outputs (file + RTMP streaming), encoders (incl. ROI hints and `EncoderCaps`), services
- Live preview (`Display` attached to a native window via HWND)
- Filters, transitions, hotkeys, fader + VU meter, audio monitoring (`Source.monitoring_enabled`, `set_monitor_only()`)
- Type lookups: display names, defaults, encoder capabilities, themed source icons (32.2+)
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

pylibobs is versioned after the libobs it bundles: **pylibobs X.Y.Z ships libobs X.Y.Z**.
A release that only changes pylibobs, on the same libobs, adds a fourth number
(X.Y.Z.1, X.Y.Z.2, …). Moving to a new libobs resets to its version.

1. Set the same version in `pyproject.toml` and `pylibobs/__init__.py`; when moving to a new
   libobs, also update `DEFAULT_OBS_TAG` in `scripts/fetch_libs.py`.
   `python scripts/check_version.py` checks they agree.
2. Tag the commit `v<version>` (e.g. `v33.0.0`) and push the tag. GitHub Actions:
   - Refuses to build unless the tag, both version strings and `DEFAULT_OBS_TAG` agree
   - Builds platform-specific wheels with bundled libobs (Windows x64 / Linux x86_64 / macOS Apple Silicon)
   - Builds the sdist
   - Publishes to PyPI via [Trusted Publishing](https://docs.pypi.org/trusted-publishers/) (no token needed in repo secrets)
   - Attaches all wheels to a GitHub Release with auto-generated notes

To set up Trusted Publishing on PyPI for this repo, register `pylibobs` as a project on PyPI,
then in *Project settings → Publishing*, add a "GitHub Actions" trusted publisher pointing at
`<owner>/pylibobs` / workflow `release.yml` / environment `pypi`.

---

Contributions welcome — PRs against `main`.
