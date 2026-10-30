"""CoreMediaIO sink delivery; real-camera test requires an explicitly chosen UID."""
from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import time
import uuid

import pytest

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(sys.platform != "darwin", reason="CoreMediaIO requires macOS")]


def _observed_red(reader):
    with selectors.DefaultSelector() as selector:
        selector.register(reader.stdout, selectors.EVENT_READ)
        assert selector.select(8), "Camera source did not deliver the red composition"
        line = reader.stdout.readline().strip()
        assert line == "RED_SEEN", line


def test_unknown_camera_uid_fails_without_allocating_an_output():
    from pylibobs.macos_camera import _native

    library = _native()
    error = ctypes.c_int32()
    pointer = library.pyc_camera_create(str(uuid.uuid4()).encode(), 640, 360, 30, 1, ctypes.byref(error))
    assert not pointer and error.value != 0


@pytest.mark.parametrize("abrupt_producer_exit", [False, True])
def test_camera_source_delivers_real_main_mix_changes(tmp_path, abrupt_producer_exit):
    """A separate camera consumer sees both authored colors, not a placeholder."""
    uid = os.environ.get("PYLIBOBS_TEST_CAMERA_UID")
    if not uid:
        pytest.skip("Set PYLIBOBS_TEST_CAMERA_UID to an installed, idle NV12-capable camera sink")
    from pylibobs import OBSContext, Scene, Source
    from pylibobs._ffi import get_lib
    from pylibobs.macos_camera import CameraOutput

    reader_binary = tmp_path / "camera-reader"
    subprocess.run([
        "clang", "-O2", "-Wall", "-Wextra", "-Werror",
        str(Path(__file__).with_name("macos_camera_client.m")),
        "-framework", "Foundation", "-framework", "CoreMediaIO",
        "-framework", "CoreMedia", "-framework", "CoreVideo", "-o", str(reader_binary),
    ], check=True, capture_output=True, timeout=30)
    reader = subprocess.Popen([str(reader_binary), uid], stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True)
    previous = None
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(reader.stdout, selectors.EVENT_READ)
            assert selector.select(8), "Camera reader did not start"
            assert reader.stdout.readline().strip() == "READER_READY"
        with OBSContext() as context:
            context.set_video(640, 360, fps_num=30)
            context.set_audio()
            context.load_modules()
            scene = Scene.create("camera-source-test")
            color = Source.create("color_source_v3", "camera-color", {
                "width": 640, "height": 360, "color": 0xFF0000FF,
            })
            scene.add(color)
            get_lib().obs_set_output_source(0, scene.as_source()._ptr)
            if abrupt_producer_exit:
                ready = tmp_path / "producer-ready"
                previous = subprocess.Popen([sys.executable, "-c", '''
import pathlib, sys, time
from pylibobs import OBSContext, Scene, Source
from pylibobs._ffi import get_lib
from pylibobs.macos_camera import CameraOutput
with OBSContext() as context:
    context.set_video(640, 360, fps_num=30)
    context.set_audio()
    context.load_modules()
    scene = Scene.create("previous-camera-producer")
    source = Source.create("color_source_v3", "red", {"width":640,"height":360,"color":0xFF0000FF})
    scene.add(source)
    get_lib().obs_set_output_source(0, scene.as_source()._ptr)
    with CameraOutput(sys.argv[1]) as output:
        deadline = time.monotonic() + 5
        while not output.frames_consumed and time.monotonic() < deadline:
            time.sleep(0.005)
        assert output.frames_consumed, output.last_error
        pathlib.Path(sys.argv[2]).touch()
        time.sleep(30)
''', uid, str(ready)], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, cwd=tmp_path)
                deadline = time.monotonic() + 10
                while not ready.exists() and previous.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.005)
                assert ready.exists(), f"Previous producer did not deliver a frame (exit={previous.poll()})"
                _observed_red(reader)
                previous.kill()
                previous.communicate(timeout=5)
            with CameraOutput(uid) as output:
                if not abrupt_producer_exit:
                    _observed_red(reader)
                with pytest.raises(RuntimeError, match="obs_reset_video"):
                    context.set_video(800, 450)
                assert context.get_current_video_info()["output_width"] == 640
                color.update({"color": 0xFFFF0000})
                stdout, stderr = reader.communicate(timeout=15)
                assert reader.returncode == 0, (stdout + stderr, output.frames_published,
                    output.frames_consumed, output.frames_dropped, output.last_error)
                result = json.loads(stdout.strip().splitlines()[-1])
                assert result["red"] and result["blue"] and result["frames"] > 1
                # After restart the old producer supplied red; one consumed
                # blue frame from its replacement already proves recovery.
                assert output.frames_consumed > 0 and not output.last_error
    finally:
        if previous is not None and previous.poll() is None:
            previous.kill()
            previous.communicate(timeout=5)
        if reader.poll() is None:
            reader.terminate()
            reader.communicate(timeout=5)
