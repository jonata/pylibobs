"""
Integration tests for the Properties API and dynamic capture configuration.

The bug being regressed: with the old (OBS <= 30) API, monitor_capture took
an integer `monitor` index. In OBS 32 it takes a string `monitor_id`.
Passing the old setting silently does nothing (the source draws black /
nothing), so the test verifies we can:

  1. Enumerate the source's list properties
  2. Read out the available choices (their display name + real value)
  3. Apply a chosen value via Source.update
  4. Confirm the new value sticks
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_monitor_capture_exposes_monitor_id_property():
    from pylibobs import (
        ComboFormat, OBSContext, Properties, PropertyType, Scene, Source,
    )
    from pylibobs._ffi import get_lib

    with OBSContext() as obs:
        obs.set_video(640, 360)
        obs.set_audio()
        obs.load_modules()

        scene = Scene.create("p_test")
        get_lib().obs_set_output_source(0, scene.as_source()._ptr)
        src = Source.create("monitor_capture", "Display")
        scene.add(src)

        props = src.get_properties()
        assert "monitor_id" in props
        prop = props["monitor_id"]
        assert prop.type == PropertyType.LIST
        assert prop.format == ComboFormat.STRING
        # At least the placeholder entry should be present.
        assert len(prop.items) >= 1

        # Pick a real (non-DUMMY) entry if available
        real = [it for it in prop.items
                if isinstance(it.value, str) and it.value and it.value != "DUMMY"]
        if not real:
            pytest.skip("No real monitors enumerated (headless / no GPU)")

        chosen = real[0]
        assert chosen.value.startswith("\\\\?\\DISPLAY")  # Windows device path

        # Apply it and confirm the setting stuck
        src.update({"monitor_id": chosen.value})
        settings = src.get_settings()
        assert settings.get_string("monitor_id") == chosen.value


def test_window_capture_exposes_window_property():
    from pylibobs import (
        ComboFormat, OBSContext, PropertyType, Scene, Source,
    )
    from pylibobs._ffi import get_lib

    with OBSContext() as obs:
        obs.set_video(640, 360)
        obs.set_audio()
        obs.load_modules()

        scene = Scene.create("p_test_w")
        get_lib().obs_set_output_source(0, scene.as_source()._ptr)
        src = Source.create("window_capture", "Window")
        scene.add(src)

        props = src.get_properties()
        assert "window" in props
        prop = props["window"]
        assert prop.type == PropertyType.LIST
        assert prop.format == ComboFormat.STRING

        # There should be at least the placeholder, often plus real windows.
        # On a CI machine there may be no windows at all, so this is loose.
        real = [it for it in prop.items
                if isinstance(it.value, str) and it.value and ":" in it.value]
        if real:
            sample = real[0]
            # Format is "<title>:<class>:<exe>"
            parts = sample.value.split(":")
            assert len(parts) >= 3
            # Apply it; libobs may normalize the value so just check it sticks.
            src.update({"window": sample.value})
            settings = src.get_settings()
            assert settings.get_string("window") == sample.value
