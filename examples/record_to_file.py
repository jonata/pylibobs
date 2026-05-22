#!/usr/bin/env python3
"""
Record the primary monitor to a file for 10 seconds.

Prerequisites:
  - OBS Studio installed (or `python scripts/fetch_libs.py` run)
  - pip install pylibobs

Usage:
    python examples/record_to_file.py [output_path]
"""

import sys
import time
from pathlib import Path

# Allow running from repo root without installing
sys.path.insert(0, str(Path(__file__).parent.parent))

from pylibobs import (
    AudioEncoder,
    OBSContext,
    OBSData,
    Output,
    Scene,
    SceneItem,
    Source,
    VideoEncoder,
)

OUTPUT_PATH = sys.argv[1] if len(sys.argv) > 1 else "recording.mkv"
DURATION_SEC = 10


def main():
    print(f"Recording {DURATION_SEC}s to{OUTPUT_PATH}")

    with OBSContext(locale="en-US") as obs:
        print(f"libobs {obs.version}")

        # 1. Configure video + audio
        obs.set_video(width=1920, height=1080, fps_num=60, fps_den=1)
        obs.set_audio(samples_per_sec=44100)

        # 2. Load plugins (encoders, sources, outputs)
        obs.load_modules()

        # 3. Build scene
        scene = Scene.create("main")

        cap_settings = OBSData({"monitor": 0, "capture_cursor": True})
        capture = Source.create("monitor_capture", "Desktop", cap_settings)
        scene.add(capture)

        # Set scene as the program output (channel 0)
        from pylibobs._ffi import get_lib
        lib = get_lib()
        from pylibobs._ffi import ffi
        lib.obs_set_output_source(0, scene.as_source()._ptr)

        # 4. Create encoders
        venc = VideoEncoder.create(
            "obs_x264", "video",
            OBSData({"rate_control": "CRF", "crf": 23, "preset": "veryfast"})
        )
        aenc = AudioEncoder.create(
            "ffmpeg_aac", "audio",
            OBSData({"bitrate": 192})
        )

        # 5. Create file output
        out = Output.create(
            "ffmpeg_muxer", "record",
            OBSData({"path": OUTPUT_PATH, "format_name": "matroska", "format_mime_type": "video/x-matroska"})
        )
        out.set_video_encoder(venc)
        out.set_audio_encoder(aenc)

        # 6. Wire up stop signal
        def on_stop(_):
            print("Output stopped.")

        out.connect_signal("stop", on_stop)

        # 7. Record
        started = out.start()
        if not started:
            err = out.last_error
            print(f"Failed to start output: {err}")
            sys.exit(1)

        print(f"Recording... ({DURATION_SEC}s)")
        for i in range(DURATION_SEC):
            time.sleep(1)
            print(f"  {i+1}/{DURATION_SEC}s  frames={out.total_frames}  bytes={out.total_bytes}")

        out.stop(wait=True)

    path = Path(OUTPUT_PATH)
    if path.exists() and path.stat().st_size > 0:
        print(f"\nSuccess! {OUTPUT_PATH} ({path.stat().st_size // 1024} KB)")
    else:
        print(f"\nWarning: output file missing or empty: {OUTPUT_PATH}")
        sys.exit(1)


if __name__ == "__main__":
    main()
