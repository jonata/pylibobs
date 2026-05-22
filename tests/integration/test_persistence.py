"""Integration tests for save/load source persistence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def test_save_load_single_source(tmp_path: Path):
    """A single source should roundtrip through obs_data."""
    from pylibobs import OBSContext, Source, save_source, load_source

    with OBSContext() as obs:
        obs.set_video(320, 180)
        obs.set_audio()
        obs.load_modules()

        src = Source.create("color_source_v3", "saved_red",
                          {"color": 0xFF0000FF, "width": 256, "height": 128})

        data = save_source(src)
        assert "saved_red" in data.to_json()

        # Drop the original
        src.release()

        # Recreate from the saved data
        restored = load_source(data)
        assert restored.name == "saved_red"
        assert restored.get_settings().get_int("width") == 256


def test_save_all_sources_to_json_file_roundtrip(tmp_path: Path):
    """Save the whole session to JSON, write to disk, re-read with parse, and
    confirm our source's name shows up in there."""
    from pylibobs import (
        OBSContext, Scene, Source,
        save_all_sources_to_json,
    )
    from pylibobs._ffi import get_lib

    scenes_file = tmp_path / "session.json"

    with OBSContext() as obs:
        obs.set_video(320, 180)
        obs.set_audio()
        obs.load_modules()

        scene = Scene.create("persist_scene")
        get_lib().obs_set_output_source(0, scene.as_source()._ptr)
        src1 = Source.create("color_source_v3", "persist_red",
                           {"color": 0xFF0000FF, "width": 100, "height": 50})
        src2 = Source.create("color_source_v3", "persist_green",
                           {"color": 0xFF00FF00, "width": 100, "height": 50})
        scene.add(src1)
        scene.add(src2)

        save_all_sources_to_json(scenes_file)

    assert scenes_file.exists()
    body = scenes_file.read_text(encoding="utf-8")

    # JSON list of objects
    parsed = json.loads(body)
    assert isinstance(parsed, list)
    names = {obj.get("name") for obj in parsed if isinstance(obj, dict)}
    assert "persist_red" in names
    assert "persist_green" in names
    assert "persist_scene" in names
