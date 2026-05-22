#!/usr/bin/env python3
"""
Stream the primary monitor to an RTMP endpoint (e.g. Twitch, YouTube, custom).

Prerequisites:
  - OBS Studio installed (or `python scripts/fetch_libs.py` run)
  - pip install pylibobs

Usage:
    python examples/stream_to_rtmp.py rtmp://live.twitch.tv/app/<STREAM_KEY>

Or split server and key:
    python examples/stream_to_rtmp.py rtmp://live.twitch.tv/app live_xxx_yyy
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pylibobs import (
    AudioEncoder,
    OBSContext,
    OBSData,
    Output,
    Scene,
    Service,
    Source,
    VideoEncoder,
)


def parse_args():
    if len(sys.argv) < 2:
        sys.exit(f"Usage: {sys.argv[0]} <rtmp_url> [stream_key]\n"
                 f"Example: {sys.argv[0]} rtmp://live.twitch.tv/app live_xxxxxxxx")
    url = sys.argv[1]
    if len(sys.argv) >= 3:
        return url, sys.argv[2]
    # URL contains the key as a path segment
    return url.rsplit("/", 1) if url.count("/") >= 3 else (url, "")


def main():
    server, key = parse_args()
    print(f"Streaming to{server} (key length {len(key)})")

    with OBSContext(locale="en-US") as obs:
        obs.set_video(width=1920, height=1080, fps_num=30)
        obs.set_audio(samples_per_sec=44100)
        obs.load_modules()

        # Scene + capture source
        scene = Scene.create("main")
        cap = Source.create("monitor_capture", "Desktop", {"monitor": 0})
        scene.add(cap)

        from pylibobs._ffi import get_lib
        get_lib().obs_set_output_source(0, scene.as_source()._ptr)

        # Encoders (CBR for streaming)
        venc = VideoEncoder.create(
            "obs_x264", "video",
            {
                "rate_control": "CBR",
                "bitrate": 6000,
                "preset": "veryfast",
                "profile": "main",
                "keyint_sec": 2,
            },
        )
        aenc = AudioEncoder.create(
            "ffmpeg_aac", "audio", {"bitrate": 160}
        )

        # Service (rtmp_common knows about Twitch/YouTube/etc.)
        service = Service.create(
            "rtmp_common", "stream",
            {"server": server, "key": key, "service": "Twitch"},
        )

        # rtmp_output sends encoded stream to the configured service
        out = Output.create("rtmp_output", "stream")
        out.set_video_encoder(venc)
        out.set_audio_encoder(aenc)
        out.set_service(service)

        # Signal hooks
        def on_start(_):  print("Stream started.")
        def on_stop(_):   print("Stream stopped.")
        def on_reconnect(_): print("Reconnecting...")

        out.connect_signal("start", on_start)
        out.connect_signal("stop", on_stop)
        out.connect_signal("reconnect", on_reconnect)

        if not out.start():
            print(f"Failed to start stream: {out.last_error}")
            sys.exit(1)

        print("Streaming. Press Ctrl-C to stop.")
        try:
            while True:
                time.sleep(2)
                print(
                    f"  active={out.active} "
                    f"frames={out.total_frames} "
                    f"dropped={out.frames_dropped} "
                    f"bytes={out.total_bytes} "
                    f"congestion={out.congestion:.2f}"
                )
        except KeyboardInterrupt:
            print("\nStopping...")
            out.stop(wait=True)


if __name__ == "__main__":
    main()
