"""Minimal step-by-step diagnostic to isolate where the recording pipeline fails."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pylibobs import OBSContext, OBSData, Scene, Source, VideoEncoder, AudioEncoder, Output
from pylibobs._ffi import ffi, get_lib


def step(name):
    print(f"[STEP] {name}", flush=True)


step("Creating OBSContext")
obs = OBSContext()
step("Calling startup()")
obs.startup()
step("Calling set_video()")
obs.set_video(width=1280, height=720, fps_num=30)
step("Calling set_audio()")
obs.set_audio()
step("Calling load_modules()")
obs.load_modules()

step("Creating scene")
scene = Scene.create("main")
step(f"  scene._ptr = {scene._ptr}")

step("Creating monitor_capture source")
cap = Source.create("monitor_capture", "Desktop", {"monitor": 0})
step(f"  source._ptr = {cap._ptr}, name={cap.name}, width={cap.width}, height={cap.height}")

step("Adding source to scene")
item = scene.add(cap)
step(f"  item._ptr = {item._ptr}")

step("Getting scene as source")
scene_src = scene.as_source()
step(f"  scene_src._ptr = {scene_src._ptr}, name={scene_src.name}")

step("Calling obs_set_output_source(0, scene_src)")
lib = get_lib()
lib.obs_set_output_source(0, scene_src._ptr)
step("  done")

step("Creating video encoder (obs_x264)")
venc = VideoEncoder.create("obs_x264", "venc", {"crf": 23, "preset": "veryfast"})
step(f"  venc._ptr = {venc._ptr}, codec={venc.codec}")

step("Creating audio encoder (ffmpeg_aac)")
aenc = AudioEncoder.create("ffmpeg_aac", "aenc", {"bitrate": 128})
step(f"  aenc._ptr = {aenc._ptr}, codec={aenc.codec}")

step("Creating ffmpeg_muxer output")
out = Output.create("ffmpeg_muxer", "rec", {"path": "diag_test.mkv"})
step(f"  out._ptr = {out._ptr}")

step("Wiring video encoder")
out.set_video_encoder(venc)
step("Wiring audio encoder")
out.set_audio_encoder(aenc)

step("Starting output")
ok = out.start()
step(f"  start() returned {ok}; last_error={out.last_error}")

if ok:
    import time
    step("Recording 3 seconds...")
    for i in range(3):
        time.sleep(1)
        step(f"  active={out.active} frames={out.total_frames} bytes={out.total_bytes}")
    step("Stopping")
    out.stop(wait=True)
    step(f"File size: {Path('diag_test.mkv').stat().st_size if Path('diag_test.mkv').exists() else 'MISSING'}")

step("Cleaning up")
obs.shutdown()
step("DONE")
