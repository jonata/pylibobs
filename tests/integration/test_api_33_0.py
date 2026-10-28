"""
Integration tests for the libobs 33.0 changes, against the real bundle:

* obs_source_set/get_monitoring_enabled, exposed as Source.monitoring_enabled,
  and how the deprecated monitoring types map onto it
* module loading now that obs_load_all_modules is an empty stub: plugins under
  OBSContext.add_module_path() paths are found and opened by pylibobs itself
"""

from __future__ import annotations

import pytest

from pylibobs import OBSContext, Source
from pylibobs._ffi import get_lib
from pylibobs._lib import get_bundled_modules, get_obs_module_dirs
from pylibobs.frame_source import enum_source_types

pytestmark = pytest.mark.integration

# enum obs_monitoring_type (obs.h)
MONITOR_NONE, MONITOR_ONLY, MONITOR_AND_OUTPUT = 0, 1, 2


@pytest.fixture
def obs():
    with OBSContext() as ctx:
        ctx.set_video(320, 180, fps_num=30)
        ctx.set_audio()
        ctx.load_modules()
        yield ctx


def test_bundled_libobs_is_33(obs):
    ver = get_lib().obs_get_version()
    assert ver >> 24 >= 33, f"libobs {ver >> 24}.{(ver >> 16) & 0xFF} predates 33.0"


def test_monitoring_enabled_round_trip(obs):
    src = Source.create("color_source_v3", "mon")
    assert src.monitoring_enabled is False
    src.monitoring_enabled = True
    assert src.monitoring_enabled is True
    src.monitoring_enabled = False
    assert src.monitoring_enabled is False


@pytest.mark.parametrize("legacy_type, enabled", [
    (MONITOR_NONE, False),
    # "Monitor only" no longer exists: it now also feeds the outputs.
    (MONITOR_ONLY, True),
    (MONITOR_AND_OUTPUT, True),
])
def test_deprecated_monitoring_types_map_to_the_switch(obs, legacy_type, enabled):
    src = Source.create("color_source_v3", f"legacy{legacy_type}")
    get_lib().obs_source_set_monitoring_type(src._ptr, legacy_type)
    assert src.monitoring_enabled is enabled
    expected = MONITOR_AND_OUTPUT if enabled else MONITOR_NONE
    assert get_lib().obs_source_get_monitoring_type(src._ptr) == expected


def test_load_all_modules_is_a_stub_in_33():
    """What pylibobs used to rely on for module paths now loads nothing."""
    bin_dir, data_dir = get_obs_module_dirs()
    with OBSContext() as ctx:
        ctx.set_video(320, 180, fps_num=30)
        ctx.set_audio()
        ctx.add_module_path(bin_dir, data_dir)
        get_lib().obs_load_all_modules()
        assert "ffmpeg_source" not in enum_source_types()


def test_modules_under_added_paths_are_loaded():
    """auto_detect=False skips the bundle; the plugins must come from the path."""
    assert get_bundled_modules(), "needs the bundled plugins as a module path"
    bin_dir, data_dir = get_obs_module_dirs()
    with OBSContext() as ctx:
        ctx.set_video(320, 180, fps_num=30)
        ctx.set_audio()
        ctx.add_module_path(bin_dir, data_dir)
        ctx.load_modules(auto_detect=False)
        types = enum_source_types()
        assert "ffmpeg_source" in types
        assert "image_source" in types
