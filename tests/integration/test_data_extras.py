"""Integration tests for OBSData defaults / iteration / save_json / apply."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def test_defaults_vs_user_values():
    from pylibobs import OBSContext, OBSData

    with OBSContext() as obs:
        obs.set_audio()
        d = OBSData()
        d.set_default_string("server", "rtmp://default.example/app")
        d.set_default_int("bitrate", 6000)
        d.set_default_bool("enabled", True)

        # Defaults are visible via the typed getters as fallbacks
        assert d.get_string("server") == "rtmp://default.example/app"
        assert d.get_int("bitrate") == 6000

        # has_user_value vs has_default_value
        assert d.has_default_value("server")
        assert not d.has_user_value("server")

        # Setting a user value overrides the default
        d["server"] = "rtmp://user.example/app"
        assert d.has_user_value("server")
        assert d.get_string("server") == "rtmp://user.example/app"
        # The default remains under the hood
        assert d.get_default_string("server") == "rtmp://default.example/app"

        d.unset_user_value("server")
        assert d.get_string("server") == "rtmp://default.example/app"


def test_iter_items_yields_known_keys():
    """iter_items walks the data via obs_data_first/next."""
    from pylibobs import OBSContext, OBSData

    with OBSContext() as obs:
        obs.set_audio()
        d = OBSData({"a": "alpha", "b": 7, "c": True})
        keys = {k for k, t in d.iter_items()}
        assert {"a", "b", "c"} <= keys


def test_save_json_to_file(tmp_path: Path):
    from pylibobs import OBSContext, OBSData

    with OBSContext() as obs:
        obs.set_audio()
        d = OBSData({"name": "tester", "rate": 192})
        out = tmp_path / "data.json"
        assert d.save_json(out) is True
        assert out.exists()

        parsed = json.loads(out.read_text())
        assert parsed["name"] == "tester"
        assert parsed["rate"] == 192


def test_apply_merges_data():
    from pylibobs import OBSContext, OBSData

    with OBSContext() as obs:
        obs.set_audio()
        a = OBSData({"x": 1, "y": 2})
        b = OBSData({"y": 99, "z": "added"})
        a.apply(b)
        assert a.get_int("x") == 1
        assert a.get_int("y") == 99
        assert a.get_string("z") == "added"
