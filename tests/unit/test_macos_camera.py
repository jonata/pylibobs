"""Native plane borrowing, bounded delivery observations and callback lifetime."""
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock, patch
import threading

import pytest

from pylibobs import _ffi
from pylibobs import macos_camera as camera


@pytest.fixture
def backend(monkeypatch):
    lib, native = Mock(), Mock()
    registered = []

    def video_info(info):
        info.output_width, info.output_height = 64, 32
        info.fps_num, info.fps_den = 30000, 1001
        return True

    lib.obs_get_video_info.side_effect = video_info
    native.pyc_camera_create.return_value = 1234
    native.pyc_camera_write.return_value = 1
    native.pyc_camera_consumed.return_value = 0
    native.pyc_camera_close.return_value = 0
    monkeypatch.setattr(_ffi, "get_lib", lambda: lib)
    monkeypatch.setattr(_ffi, "register_wrapper", registered.append)
    monkeypatch.setattr(camera, "_native", lambda: native)
    yield SimpleNamespace(lib=lib, native=native, registered=registered)
    for output in registered:
        output.close()
    camera._device_uids.clear()


def test_subscribes_to_native_nv12_planes_with_rational_frame_rate(backend):
    output = camera.CameraOutput("native-device-uid")
    assert backend.native.pyc_camera_create.call_args.args[1:5] == (64, 32, 30000, 1001)
    conversion, callback, parameter = backend.lib.obs_add_raw_video_callback.call_args.args
    assert (conversion.width, conversion.height, conversion.format, conversion.range, conversion.colorspace) == (64, 32, 2, 1, 2)
    ffi = _ffi.ffi
    frame = ffi.new("struct video_data *")
    y, uv = ffi.new("uint8_t[]", 64 * 32), ffi.new("uint8_t[]", 64 * 16)
    frame.data[0], frame.data[1] = y, uv
    frame.linesize[0], frame.linesize[1], frame.timestamp = 64, 64, 123000000
    callback(parameter, frame)
    backend.native.pyc_camera_write.assert_called_once_with(1234, int(ffi.cast("uintptr_t", y)), 64,
                                                           int(ffi.cast("uintptr_t", uv)), 64, 123000000)
    assert output.frames_published == 1 and output.frames_consumed == 0
    backend.native.pyc_camera_consumed.return_value = 1
    assert output.frames_consumed == 1


def test_busy_sink_drops_without_marking_output_failed(backend):
    output = camera.CameraOutput("device")
    backend.native.pyc_camera_write.return_value = 0
    _, callback, parameter = backend.lib.obs_add_raw_video_callback.call_args.args
    callback(parameter, _ffi.ffi.new("struct video_data *"))
    assert output.active and output.frames_dropped == 1 and output.frames_published == 0


def test_disconnection_stops_future_publication_and_preserves_native_diagnostic(backend):
    output = camera.CameraOutput("device")
    backend.native.pyc_camera_write.return_value = -1
    backend.native.pyc_camera_error.return_value = -12743
    _, callback, parameter = backend.lib.obs_add_raw_video_callback.call_args.args
    frame = _ffi.ffi.new("struct video_data *")
    callback(parameter, frame)
    callback(parameter, frame)
    assert not output.active and "-12743" in output.last_error
    backend.native.pyc_camera_write.assert_called_once()


def test_close_waits_for_native_callback_without_holding_its_lock(backend):
    output = camera.CameraOutput("device")
    _, callback, parameter = backend.lib.obs_add_raw_video_callback.call_args.args
    calls = []

    def remove(*_arguments):
        worker = threading.Thread(target=lambda: callback(parameter, _ffi.ffi.new("struct video_data *")))
        worker.start()
        worker.join(1)
        assert not worker.is_alive(), "close blocked a native video callback"
        calls.append("removed")

    backend.lib.obs_remove_raw_video_callback.side_effect = remove
    backend.native.pyc_camera_close.side_effect = lambda _pointer: calls.append("closed")
    output.close()
    output.close()
    assert calls == ["removed", "closed"]
    assert not output.active and output.frames_consumed == 0


def test_callback_registration_failure_releases_connected_sink(backend):
    backend.lib.obs_add_raw_video_callback.side_effect = RuntimeError("registration rejected")
    with pytest.raises(RuntimeError, match="registration rejected"):
        camera.CameraOutput("device")
    backend.native.pyc_camera_close.assert_called_once_with(1234)


def test_conversion_allocation_failure_releases_sink_and_device_reservation(backend, monkeypatch):
    allocate = _ffi.ffi.new

    def fail_conversion(kind, *arguments):
        if kind == "struct video_scale_info *":
            raise MemoryError("conversion allocation failed")
        return allocate(kind, *arguments)

    monkeypatch.setattr(_ffi.ffi, "new", fail_conversion)
    with pytest.raises(MemoryError, match="conversion allocation failed"):
        camera.CameraOutput("device")
    backend.native.pyc_camera_close.assert_called_once_with(1234)
    assert "device" not in camera._device_uids


def test_failed_native_open_releases_device_reservation(backend):
    backend.native.pyc_camera_create.return_value = None
    with pytest.raises(OSError):
        camera.CameraOutput("device")
    backend.native.pyc_camera_close.assert_not_called()
    backend.native.pyc_camera_create.return_value = 1234
    output = camera.CameraOutput("device")
    assert output.active


def test_duplicate_output_cannot_stop_an_existing_owner(backend):
    first = camera.CameraOutput("device")
    with pytest.raises(RuntimeError, match="already owns"):
        camera.CameraOutput("device")
    backend.native.pyc_camera_create.assert_called_once()
    backend.native.pyc_camera_close.assert_not_called()
    assert first.active
    first.close()
    assert camera.CameraOutput("device").active


def test_repeated_close_cannot_release_a_successors_reservation(backend):
    first = camera.CameraOutput("device")
    first.close()
    successor = camera.CameraOutput("device")

    first.close()

    with pytest.raises(RuntimeError, match="already owns"):
        camera.CameraOutput("device")
    assert successor.active
    assert backend.native.pyc_camera_create.call_count == 2
    backend.native.pyc_camera_close.assert_called_once()
    successor.close()
    assert camera.CameraOutput("device").active


@pytest.mark.parametrize("close_previous_owner", [False, True])
def test_concurrent_constructors_reserve_the_uid_before_native_open(backend, close_previous_owner):
    if close_previous_owner:
        previous = camera.CameraOutput("device")
        previous.close()
        backend.native.pyc_camera_create.reset_mock()
    entered, release = threading.Event(), threading.Event()
    results = []

    def open_native(*_arguments):
        entered.set()
        assert release.wait(2)
        return 1234

    def create():
        results.append(camera.CameraOutput("device"))

    backend.native.pyc_camera_create.side_effect = open_native
    worker = threading.Thread(target=create)
    worker.start()
    try:
        assert entered.wait(1)
        if close_previous_owner:
            previous.close()
        with pytest.raises(RuntimeError, match="already owns"):
            camera.CameraOutput("device")
        backend.native.pyc_camera_create.assert_called_once()
    finally:
        release.set()
        worker.join(2)
    assert not worker.is_alive() and results[0].active


@pytest.mark.parametrize("stop_status", [0, -1234])
def test_concurrent_close_retains_reservation_until_native_stop_finishes(backend, stop_status):
    output = camera.CameraOutput("device")
    entered, release = threading.Event(), threading.Event()

    def stop_native(_pointer):
        entered.set()
        assert release.wait(2)
        return stop_status

    backend.native.pyc_camera_close.side_effect = stop_native
    with ThreadPoolExecutor(max_workers=2) as workers:
        first_close = workers.submit(output.close)
        try:
            assert entered.wait(1)
            second_close = workers.submit(output.close)
            with pytest.raises(RuntimeError, match="already owns"):
                camera.CameraOutput("device")
        finally:
            release.set()
        first_close.result(timeout=2)
        second_close.result(timeout=2)

    backend.lib.obs_remove_raw_video_callback.assert_called_once()
    backend.native.pyc_camera_close.assert_called_once()
    assert not output.active
    if stop_status:
        with pytest.raises(RuntimeError, match="already owns"):
            camera.CameraOutput("device")
    else:
        assert camera.CameraOutput("device").active


def test_native_close_failure_is_observable_after_resources_detach(backend):
    output = camera.CameraOutput("device")
    backend.native.pyc_camera_close.return_value = -1234
    output.close()
    output.close()
    assert not output.active and "-1234" in output.last_error
    assert output not in camera._outputs
    backend.native.pyc_camera_close.assert_called_once()
    with pytest.raises(RuntimeError, match="already owns"):
        camera.CameraOutput("device")


def test_callback_removal_failure_retains_owner_for_retry(backend):
    output = camera.CameraOutput("device")
    with patch.object(backend.lib, "obs_remove_raw_video_callback", side_effect=RuntimeError("removal rejected")):
        with pytest.raises(RuntimeError, match="removal rejected"):
            output.close()
    backend.native.pyc_camera_close.assert_not_called()
    assert output in camera._outputs
    with pytest.raises(RuntimeError, match="already owns"):
        camera.CameraOutput("device")
    output.close()
    assert output not in camera._outputs
    assert camera.CameraOutput("device").active


@pytest.mark.parametrize("uid", [None, "", "abc\0def", 42])
def test_invalid_device_identity_is_rejected_before_native_allocation(backend, uid):
    with pytest.raises(ValueError):
        camera.CameraOutput(uid)
    backend.native.pyc_camera_create.assert_not_called()


def test_camera_requires_initialized_video(backend):
    backend.lib.obs_get_video_info.return_value = False
    backend.lib.obs_get_video_info.side_effect = None
    with pytest.raises(RuntimeError, match="Initialize OBS video"):
        camera.CameraOutput("device")
    backend.native.pyc_camera_create.assert_not_called()
