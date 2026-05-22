"""
OBSContext — lifecycle manager for the libobs runtime.

Usage::

    with OBSContext() as obs:
        obs.set_video(width=1920, height=1080, fps_num=60)
        obs.set_audio()
        obs.load_modules()
        ...
"""

from __future__ import annotations

import platform
from enum import IntEnum

from ._ffi import ffi, get_lib, mark_alive, mark_dead, release_all_wrappers


# libobs MAX_CHANNELS is 64 in the public ABI; conservatively clear that many.
_MAX_OUTPUT_CHANNELS = 64
from ._lib import get_obs_data_dir, get_obs_module_dirs


class VideoFormat(IntEnum):
    NONE  = 0
    I420  = 1
    NV12  = 2
    YVYU  = 3
    YUY2  = 4
    UYVY  = 5
    RGBA  = 6
    BGRA  = 7
    BGRX  = 8
    Y800  = 9
    I444  = 10
    BGR3  = 11
    I422  = 12


class Speakers(IntEnum):
    UNKNOWN  = 0
    MONO     = 1
    STEREO   = 2
    S2POINT1 = 3
    S4POINT0 = 4
    S4POINT1 = 5
    S5POINT1 = 6
    S7POINT1 = 8


class ScaleType(IntEnum):
    DISABLE  = 0
    POINT    = 1
    BICUBIC  = 2
    BILINEAR = 3
    LANCZOS  = 4
    AREA     = 5


class ColorSpace(IntEnum):
    DEFAULT   = 0
    CS601     = 1
    CS709     = 2
    SRGB      = 3
    CS2100_PQ = 4
    CS2100_HLG= 5


class VideoRange(IntEnum):
    DEFAULT = 0
    PARTIAL = 1
    FULL    = 2


_VIDEO_INIT_ERR = {
    0:  "success",
    -1: "not supported (check graphics driver/module)",
    -2: "invalid parameters",
    -3: "video already active",
    -4: "graphics module not found",
    -5: "general failure",
}

_DEFAULT_GRAPHICS_MODULE = {
    "Windows": "libobs-d3d11",
    "Linux":   "libobs-opengl",
    "Darwin":  "libobs-opengl",
}


class OBSContext:
    """
    Context manager that owns the libobs runtime lifecycle.

    Parameters
    ----------
    locale:             BCP-47 locale string (e.g. "en-US").
    module_config_path: Directory where OBS modules store their config.
                        Defaults to the OS-standard OBS config dir.
    """

    def __init__(
        self,
        locale: str = "en-US",
        module_config_path: str | None = None,
    ) -> None:
        self._locale = locale
        self._module_config_path = module_config_path or _default_config_dir()
        self._started = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def startup(self) -> None:
        if self._started:
            return
        lib = get_lib()
        if lib.obs_initialized():
            # Some other code already initialised libobs; don't fight it.
            self._started = True
            return
        locale_b = self._locale.encode()
        config_b = self._module_config_path.encode() if self._module_config_path else ffi.NULL
        ok = lib.obs_startup(locale_b, config_b, ffi.NULL)
        if not ok:
            raise RuntimeError("obs_startup() returned false — libobs failed to initialize.")
        self._started = True
        mark_alive()

        # Register the bundled data path so shader effects etc. resolve.
        data_dir = get_obs_data_dir()
        if data_dir:
            lib.obs_add_data_path((data_dir.rstrip("/\\") + "/").encode())
            # libobs subdir for shaders
            libobs_sub = data_dir.rstrip("/\\") + "/libobs/"
            lib.obs_add_data_path(libobs_sub.encode())

    def shutdown(self) -> None:
        """
        Shut down libobs cleanly.

        Order matters here — obs_shutdown() does not gracefully handle
        outstanding refcounts on sources/outputs/etc.:
          1. Stop and clear all output channels (drops libobs's internal refs)
          2. Release every Python wrapper we created (drops our refs)
          3. Run a gc pass so any remaining wrappers get finalized
          4. Call obs_shutdown() — now all refs are gone
        """
        if not self._started:
            return

        lib = get_lib()
        try:
            # Step 1: clear all output channels
            for ch in range(_MAX_OUTPUT_CHANNELS):
                try:
                    lib.obs_set_output_source(ch, ffi.NULL)
                except Exception:
                    pass

            # Step 2 + 3: release wrappers, then gc anything else
            release_all_wrappers()
            import gc
            gc.collect()

            # Some sources (e.g. text_gdiplus) defer GPU-resource destruction
            # to libobs's graphics thread. Give it time to drain before
            # obs_shutdown tears down that thread — otherwise the in-flight
            # destroy callback can run on a torn-down graphics context.
            import time
            time.sleep(0.2)

            # Step 4: tear down libobs
            lib.obs_shutdown()
        finally:
            mark_dead()
            self._started = False

    # ------------------------------------------------------------------
    # Video / audio reset
    # ------------------------------------------------------------------

    def set_video(
        self,
        width: int = 1920,
        height: int = 1080,
        fps_num: int = 30,
        fps_den: int = 1,
        output_width: int | None = None,
        output_height: int | None = None,
        output_format: VideoFormat = VideoFormat.NV12,
        colorspace: ColorSpace = ColorSpace.DEFAULT,
        range: VideoRange = VideoRange.DEFAULT,
        scale_type: ScaleType = ScaleType.BICUBIC,
        adapter: int = 0,
        graphics_module: str | None = None,
    ) -> None:
        """Call obs_reset_video with the given parameters."""
        lib = get_lib()
        ovi = ffi.new("struct obs_video_info *")

        gfx = graphics_module or _DEFAULT_GRAPHICS_MODULE.get(platform.system(), "libobs-opengl")
        ovi.graphics_module = ffi.new("char[]", gfx.encode())
        ovi.fps_num        = fps_num
        ovi.fps_den        = fps_den
        ovi.base_width     = width
        ovi.base_height    = height
        ovi.output_width   = output_width or width
        ovi.output_height  = output_height or height
        ovi.output_format  = int(output_format)
        ovi.gpu_conversion = True
        ovi.colorspace     = int(colorspace)
        ovi.range          = int(range)
        ovi.scale_type     = int(scale_type)
        ovi.adapter        = adapter

        err = lib.obs_reset_video(ovi)
        if err != 0:
            msg = _VIDEO_INIT_ERR.get(err, f"unknown error {err}")
            raise RuntimeError(f"obs_reset_video failed: {msg}")

    def set_audio(
        self,
        samples_per_sec: int = 44100,
        speakers: Speakers = Speakers.STEREO,
    ) -> None:
        """Call obs_reset_audio with the given parameters."""
        lib = get_lib()
        oai = ffi.new("struct obs_audio_info *")
        oai.samples_per_sec = samples_per_sec
        oai.speakers        = int(speakers)
        ok = lib.obs_reset_audio(oai)
        if not ok:
            raise RuntimeError("obs_reset_audio failed.")

    # ------------------------------------------------------------------
    # Module loading
    # ------------------------------------------------------------------

    def add_module_path(self, bin_path: str, data_path: str) -> None:
        lib = get_lib()
        lib.obs_add_module_path(bin_path.encode(), data_path.encode())

    def load_modules(self, auto_detect: bool = True) -> None:
        """Load OBS plugin modules from standard install paths."""
        lib = get_lib()
        if auto_detect:
            bin_dir, data_dir = get_obs_module_dirs()
            if bin_dir:
                lib.obs_add_module_path(bin_dir.encode(), data_dir.encode())
        lib.obs_load_all_modules()
        lib.obs_post_load_modules()

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def initialized(self) -> bool:
        return bool(get_lib().obs_initialized())

    @property
    def version(self) -> str:
        s = get_lib().obs_get_version_string()
        return ffi.string(s).decode() if s != ffi.NULL else ""

    # ------------------------------------------------------------------
    # Video timing / state introspection
    # ------------------------------------------------------------------

    @property
    def video_frame_time_ns(self) -> int:
        """Current frame's timestamp in nanoseconds (from libobs's video clock)."""
        return int(get_lib().obs_get_video_frame_time())

    @property
    def hdr_nominal_peak_level(self) -> float:
        return float(get_lib().obs_get_video_hdr_nominal_peak_level())

    @property
    def sdr_white_level(self) -> float:
        return float(get_lib().obs_get_video_sdr_white_level())

    def set_video_levels(self, sdr_white: float, hdr_nominal_peak: float) -> None:
        get_lib().obs_set_video_levels(float(sdr_white), float(hdr_nominal_peak))

    def get_current_video_info(self):
        """Read the currently-active video settings as a dict, or None if
        video isn't initialised yet."""
        ovi = ffi.new("struct obs_video_info *")
        if not get_lib().obs_get_video_info(ovi):
            return None
        return {
            "fps_num":       int(ovi.fps_num),
            "fps_den":       int(ovi.fps_den),
            "base_width":    int(ovi.base_width),
            "base_height":   int(ovi.base_height),
            "output_width":  int(ovi.output_width),
            "output_height": int(ovi.output_height),
            "output_format": int(ovi.output_format),
            "adapter":       int(ovi.adapter),
            "gpu_conversion": bool(ovi.gpu_conversion),
            "colorspace":    int(ovi.colorspace),
            "range":         int(ovi.range),
            "scale_type":    int(ovi.scale_type),
        }

    # ------------------------------------------------------------------
    # Audio state
    # ------------------------------------------------------------------

    def reset_audio_monitoring(self) -> None:
        """Re-enumerate audio monitoring devices (call after USB headset
        plug/unplug)."""
        get_lib().obs_reset_audio_monitoring()

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "OBSContext":
        self.startup()
        return self

    def __exit__(self, *_) -> None:
        self.shutdown()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _default_config_dir() -> str:
    import os
    system = platform.system()
    if system == "Windows":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
        return os.path.join(base, "obs-studio", "plugin-config")
    elif system == "Darwin":
        return os.path.expanduser("~/Library/Application Support/obs-studio/plugin-config")
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
        return os.path.join(xdg, "obs-studio", "plugin-config")
