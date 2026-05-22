"""Integration tests for Service — make sure URL/key/etc. still work
after we removed the obs_service_get_url/key/username/password calls
(they were removed from OBS 32; we now read them from the settings dict)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_rtmp_service_url_key_read_back_from_settings():
    from pylibobs import OBSContext, Service

    with OBSContext() as obs:
        obs.set_video(320, 180)
        obs.set_audio()
        obs.load_modules()

        svc = Service.create("rtmp_custom", "test_rtmp", {
            "server":   "rtmp://stream.example.com/live",
            "key":      "secret_stream_key_12345",
            "username": "user",
            "password": "pass",
        })

        assert svc.url == "rtmp://stream.example.com/live"
        assert svc.key == "secret_stream_key_12345"
        assert svc.username == "user"
        assert svc.password == "pass"

        assert svc.id == "rtmp_custom"
        assert svc.name == "test_rtmp"
