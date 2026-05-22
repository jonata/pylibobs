"""Integration tests for hotkey registration and triggering."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_register_frontend_hotkey_and_trigger():
    """Register a frontend hotkey, fire it programmatically, verify callback ran."""
    from pylibobs import Hotkey, OBSContext

    with OBSContext() as obs:
        obs.set_video(640, 360)
        obs.set_audio()
        obs.load_modules()

        events: list[bool] = []
        hk = Hotkey.register_frontend(
            "test.start_recording",
            "Start the test recording",
            lambda pressed: events.append(pressed),
        )
        assert hk.id != (1 << 64) - 1, "Registration returned INVALID_HOTKEY_ID"
        assert hk.name == "test.start_recording"

        # Fire programmatically
        hk.trigger(pressed=True)
        hk.trigger(pressed=False)

        assert events == [True, False], f"Got events: {events}"

        # Unregister and re-firing should now be a no-op
        hk.unregister()
        before = len(events)
        try:
            hk.trigger(pressed=True)   # should silently do nothing
        except Exception:
            pass  # If libobs decides to error, that's fine too
        # callback shouldn't have fired again
        assert len(events) == before


def test_register_source_hotkey():
    """Hotkeys can be attached to sources (saved with the source's settings)."""
    from pylibobs import Hotkey, OBSContext, Source

    with OBSContext() as obs:
        obs.set_video(640, 360)
        obs.set_audio()
        obs.load_modules()

        src = Source.create("color_source_v3", "hk_src",
                          {"color": 0xFF333333, "width": 64, "height": 64})

        events: list[bool] = []
        hk = Hotkey.register_source(
            src, "test.src_toggle", "Toggle the source",
            lambda pressed: events.append(pressed),
        )
        hk.trigger(True)
        hk.trigger(False)
        assert events == [True, False]


def test_key_name_to_code_roundtrip():
    """OBS's named-key API should roundtrip OBS_KEY_F1, OBS_KEY_SPACE, etc."""
    from pylibobs import OBSContext, key_from_name, key_to_name

    with OBSContext() as obs:
        obs.set_video(640, 360)
        obs.set_audio()
        # Don't load modules — these calls don't need them

        for n in ("OBS_KEY_F1", "OBS_KEY_SPACE", "OBS_KEY_A", "OBS_KEY_RETURN"):
            code = key_from_name(n)
            assert code > 0, f"{n} resolved to {code}"
            back = key_to_name(code)
            assert back == n, f"{n} → {code} → {back}"

        # Unknown key returns code 0 (OBS_KEY_NONE)
        assert key_from_name("NOT_A_REAL_KEY") == 0


def test_inject_key_event_routes_through_hotkey():
    """obs_hotkey_inject_event fires the routed callback if a binding matches.

    Without setting up a binding (which requires obs_hotkey_load with a
    properly formed obs_data_array), the inject is essentially a no-op for
    the test. Verify it doesn't crash.
    """
    from pylibobs import KeyModifier, OBSContext, inject_key_event

    with OBSContext() as obs:
        obs.set_video(640, 360)
        obs.set_audio()
        obs.load_modules()

        # Should not raise
        inject_key_event("OBS_KEY_F1", KeyModifier.SHIFT, pressed=True)
        inject_key_event("OBS_KEY_F1", KeyModifier.SHIFT, pressed=False)
