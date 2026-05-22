"""
pylibobs — Python bindings for libobs (OBS Studio core library).

Quick start::

    from pylibobs import OBSContext, OBSData, Source, Scene, Output, VideoEncoder, AudioEncoder

    with OBSContext() as obs:
        obs.set_video(width=1920, height=1080, fps_num=60)
        obs.set_audio()
        obs.load_modules()

        scene = Scene.create("main")
        cap = Source.create("monitor_capture", "Desktop")
        scene.add(cap)

        venc = VideoEncoder.create("obs_x264", "h264", {"crf": 23})
        aenc = AudioEncoder.create("ffmpeg_aac", "aac", {"bitrate": 192})

        out = Output.create("ffmpeg_muxer", "rec", {"path": "output.mkv"})
        out.set_video_encoder(venc)
        out.set_audio_encoder(aenc)
        out.start()

        import time; time.sleep(10)
        out.stop()

License: GPL-2.0-or-later (inherited from libobs).
"""

from .context import OBSContext, VideoFormat, Speakers, ColorSpace, VideoRange, ScaleType  # noqa: F401
from .data import OBSData
from .source import Source
from .scene import Scene, SceneItem
from .encoder import VideoEncoder, AudioEncoder
from .service import Service
from .output import Output
from .display import Display, render_main_texture_letterboxed
from .properties import (
    Properties, Property, PropertyType, ComboFormat, ListItem,
    IntRange, FloatRange, TextInfo, PathInfo,
)
from .scene import Alignment, BoundsType, BlendingMode, BlendingMethod, TransformInfo
from .callbacks import (
    add_source_audio_capture_callback, remove_source_audio_capture_callback,
    add_raw_audio_callback, remove_raw_audio_callback,
    add_raw_video_callback, remove_raw_video_callback,
    add_main_render_callback, remove_main_render_callback,
    add_tick_callback, remove_tick_callback, clear_all_callbacks,
)
from .persistence import (
    OBSDataArray, save_source, load_source,
    save_all_sources, load_all_sources,
    save_all_sources_to_json, load_all_sources_from_json,
)
from .resampler import AudioResampler, AudioFormat
from .remux import MediaRemux, remux
from .filters import Filter, enum_filter_types
from .transitions import Transition, TransitionMode, enum_transition_types
from .audio_mixer import VolumeMeter, Fader, PeakMeterType, FaderType
from .hotkeys import (
    Hotkey, KeyModifier, key_from_name, key_to_name, inject_key_event,
    enable_callback_rerouting, enable_background_press,
)
from .enumeration import (
    AudioMonitoringDevice, InputType,
    enum_sources, enum_scenes, enum_all_sources,
    enum_source_types, enum_input_types, enum_input_types2,
    enum_encoder_types, enum_output_types, enum_service_types,
    get_source_display_name, get_output_display_name,
    get_encoder_display_name, get_service_display_name,
    get_source_defaults, get_encoder_defaults,
    get_service_defaults, get_output_defaults,
    enum_audio_monitoring_devices, audio_monitoring_available,
    set_audio_monitoring_device, get_audio_monitoring_device,
)

__version__ = "0.0.1"
__all__ = [
    "OBSContext",
    "OBSData",
    "Source",
    "Scene",
    "SceneItem",
    "VideoEncoder",
    "AudioEncoder",
    "Service",
    "Output",
    "Display",
    "render_main_texture_letterboxed",
    "Properties",
    "Property",
    "PropertyType",
    "ComboFormat",
    "ListItem",
    "Filter",
    "Transition",
    "TransitionMode",
    "VolumeMeter",
    "Fader",
    "PeakMeterType",
    "FaderType",
    "Hotkey",
    "KeyModifier",
    "AudioMonitoringDevice",
    "InputType",
    "key_from_name",
    "key_to_name",
    "inject_key_event",
    "enum_sources",
    "enum_scenes",
    "enum_all_sources",
    "enum_source_types",
    "enum_input_types",
    "enum_input_types2",
    "enum_filter_types",
    "enum_transition_types",
    "enum_encoder_types",
    "enum_output_types",
    "enum_service_types",
    "get_source_display_name",
    "get_output_display_name",
    "get_encoder_display_name",
    "get_service_display_name",
    "get_source_defaults",
    "get_encoder_defaults",
    "get_service_defaults",
    "get_output_defaults",
    "enum_audio_monitoring_devices",
    "audio_monitoring_available",
    "set_audio_monitoring_device",
    "get_audio_monitoring_device",
    # Transform
    "Alignment",
    "BoundsType",
    "BlendingMode",
    "BlendingMethod",
    "TransformInfo",
    # Properties
    "IntRange",
    "FloatRange",
    "TextInfo",
    "PathInfo",
    # Callbacks
    "add_source_audio_capture_callback",
    "remove_source_audio_capture_callback",
    "add_raw_audio_callback",
    "remove_raw_audio_callback",
    "add_raw_video_callback",
    "remove_raw_video_callback",
    "add_main_render_callback",
    "remove_main_render_callback",
    "add_tick_callback",
    "remove_tick_callback",
    "clear_all_callbacks",
    # Persistence
    "OBSDataArray",
    "save_source",
    "load_source",
    "save_all_sources",
    "load_all_sources",
    "save_all_sources_to_json",
    "load_all_sources_from_json",
    # Resampler / Remux
    "AudioResampler",
    "AudioFormat",
    "MediaRemux",
    "remux",
    "VideoFormat",
    "Speakers",
    "ColorSpace",
    "VideoRange",
    "ScaleType",
]
