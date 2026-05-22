"""
C declarations for libobs, formatted for cffi cdef().

Extracted and cleaned from OBS Studio public headers (libobs/obs.h and related).
Preprocessor macros are replaced with inline values; only cffi-compatible syntax is used.
Targets OBS Studio 30.x API.
"""

# ---------------------------------------------------------------------------
# Common typedefs and opaque structs
# ---------------------------------------------------------------------------
_COMMON = """
    typedef _Bool bool;

    /* Opaque libobs object types */
    typedef struct video_output  video_t;
    typedef struct audio_output  audio_t;
    typedef struct gs_texture    gs_texture_t;
    typedef struct gs_swapchain  gs_swapchain_t;
    typedef struct obs_source    obs_source_t;
    typedef struct obs_scene     obs_scene_t;
    typedef struct obs_scene_item obs_sceneitem_t;
    typedef struct obs_output    obs_output_t;
    typedef struct obs_encoder   obs_encoder_t;
    typedef struct obs_service   obs_service_t;
    typedef struct obs_data      obs_data_t;
    typedef struct obs_data_array obs_data_array_t;
    typedef struct obs_properties obs_properties_t;
    typedef struct obs_property  obs_property_t;
    typedef struct signal_handler signal_handler_t;
    typedef struct proc_handler  proc_handler_t;
    typedef struct obs_display   obs_display_t;

    /* calldata for signal callbacks */
    typedef struct calldata {
        uint8_t *stack;
        size_t   size;
        size_t   fixed_size;
        bool     dynamic_size;
    } calldata_t;

    typedef void (*signal_callback_t)(void *data, calldata_t *cd);

    /* Hotkey + fader + volmeter typedefs */
    typedef size_t obs_hotkey_id;
    typedef struct obs_hotkey obs_hotkey_t;
    typedef struct obs_fader   obs_fader_t;
    typedef struct obs_volmeter obs_volmeter_t;

    typedef int  obs_key_t;          /* obs_key enum, plain int in C */
    struct obs_key_combination {
        uint32_t   modifiers;
        obs_key_t  key;
    };
    typedef struct obs_key_combination obs_key_combination_t;

    typedef void (*obs_hotkey_func)(void *data, obs_hotkey_id id,
                                    obs_hotkey_t *hotkey, bool pressed);

    typedef void (*obs_volmeter_updated_t)(void *param,
        const float magnitude[8],
        const float peak[8],
        const float input_peak[8]);

    typedef void (*obs_fader_changed_t)(void *param, float db);

    /* Enumeration callbacks */
    typedef bool (*obs_enum_source_cb_t)(void *data, obs_source_t *source);
    typedef bool (*obs_enum_audio_devices_cb_t)(void *data, const char *name,
                                                const char *id);
"""

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
_ENUMS = """
    enum obs_video_err {
        OBS_VIDEO_SUCCESS         =  0,
        OBS_VIDEO_NOT_SUPPORTED   = -1,
        OBS_VIDEO_INVALID_PARAM   = -2,
        OBS_VIDEO_CURRENTLY_ACTIVE= -3,
        OBS_VIDEO_MODULE_NOT_FOUND= -4,
        OBS_VIDEO_FAIL            = -5
    };

    enum video_format {
        VIDEO_FORMAT_NONE = 0,
        VIDEO_FORMAT_I420,
        VIDEO_FORMAT_NV12,
        VIDEO_FORMAT_YVYU,
        VIDEO_FORMAT_YUY2,
        VIDEO_FORMAT_UYVY,
        VIDEO_FORMAT_RGBA,
        VIDEO_FORMAT_BGRA,
        VIDEO_FORMAT_BGRX,
        VIDEO_FORMAT_Y800,
        VIDEO_FORMAT_I444,
        VIDEO_FORMAT_BGR3,
        VIDEO_FORMAT_I422,
        VIDEO_FORMAT_I40A,
        VIDEO_FORMAT_I42A,
        VIDEO_FORMAT_YUVA,
        VIDEO_FORMAT_AYUV,
        VIDEO_FORMAT_I010,
        VIDEO_FORMAT_P010,
        VIDEO_FORMAT_I210,
        VIDEO_FORMAT_I412,
        VIDEO_FORMAT_YA2L,
        VIDEO_FORMAT_P216,
        VIDEO_FORMAT_P416,
        VIDEO_FORMAT_V210,
        VIDEO_FORMAT_R10L
    };

    enum speaker_layout {
        SPEAKERS_UNKNOWN  = 0,
        SPEAKERS_MONO     = 1,
        SPEAKERS_STEREO   = 2,
        SPEAKERS_2POINT1  = 3,
        SPEAKERS_4POINT0  = 4,
        SPEAKERS_4POINT1  = 5,
        SPEAKERS_5POINT1  = 6,
        SPEAKERS_7POINT1  = 8
    };

    enum obs_scale_type {
        OBS_SCALE_DISABLE,
        OBS_SCALE_POINT,
        OBS_SCALE_BICUBIC,
        OBS_SCALE_BILINEAR,
        OBS_SCALE_LANCZOS,
        OBS_SCALE_AREA
    };

    enum video_colorspace {
        VIDEO_CS_DEFAULT  = 0,
        VIDEO_CS_601      = 1,
        VIDEO_CS_709      = 2,
        VIDEO_CS_SRGB     = 3,
        VIDEO_CS_2100_PQ  = 4,
        VIDEO_CS_2100_HLG = 5
    };

    enum video_range_type {
        VIDEO_RANGE_DEFAULT = 0,
        VIDEO_RANGE_PARTIAL = 1,
        VIDEO_RANGE_FULL    = 2
    };

    enum obs_encoder_type {
        OBS_ENCODER_AUDIO,
        OBS_ENCODER_VIDEO
    };

    enum obs_output_flags {
        OBS_OUTPUT_VIDEO            = 1,
        OBS_OUTPUT_AUDIO            = 2,
        OBS_OUTPUT_AV               = 3,
        OBS_OUTPUT_ENCODED          = 4,
        OBS_OUTPUT_SERVICE          = 8,
        OBS_OUTPUT_MULTI_TRACK      = 16,
        OBS_OUTPUT_CAN_PAUSE        = 32
    };

    enum gs_color_format {
        GS_UNKNOWN = 0,
        GS_A8,
        GS_R8,
        GS_RGBA,
        GS_BGRX,
        GS_BGRA,
        GS_R10G10B10A2,
        GS_RGBA16,
        GS_R16,
        GS_RGBA16F,
        GS_RGBA32F,
        GS_RG16F,
        GS_RG32F,
        GS_R16F,
        GS_R32F,
        GS_DXT1,
        GS_DXT3,
        GS_DXT5,
        GS_R8G8,
        GS_RGBA_UNORM,
        GS_BGRX_UNORM,
        GS_BGRA_UNORM,
        GS_RG16
    };

    enum gs_zstencil_format {
        GS_ZS_NONE = 0,
        GS_Z16,
        GS_Z24_S8,
        GS_Z32F,
        GS_Z32F_S8X24
    };
"""

# ---------------------------------------------------------------------------
# Structs
# ---------------------------------------------------------------------------
_STRUCTS = """
    /* IMPORTANT: field order must match libobs/obs.h exactly.
       OBS 31+ moved `adapter` to sit between output_format and gpu_conversion. */
    struct obs_video_info {
        const char            *graphics_module;
        uint32_t               fps_num;
        uint32_t               fps_den;
        uint32_t               base_width;
        uint32_t               base_height;
        uint32_t               output_width;
        uint32_t               output_height;
        enum video_format      output_format;
        uint32_t               adapter;
        bool                   gpu_conversion;
        enum video_colorspace  colorspace;
        enum video_range_type  range;
        enum obs_scale_type    scale_type;
    };

    struct obs_audio_info {
        uint32_t            samples_per_sec;
        enum speaker_layout speakers;
    };

    /* Windows: struct gs_window is { void *hwnd; }
       On Linux/macOS this struct contains different fields — for now we
       only declare the Windows layout. */
    struct gs_window {
        void *hwnd;
    };

    struct gs_init_data {
        struct gs_window           window;
        uint32_t                   cx;
        uint32_t                   cy;
        uint32_t                   num_backbuffers;
        enum gs_color_format       format;
        enum gs_zstencil_format    zsformat;
        uint32_t                   adapter;
    };
"""

# ---------------------------------------------------------------------------
# Core lifecycle functions
# ---------------------------------------------------------------------------
_CORE = """
    bool        obs_startup(const char *locale, const char *module_config_path,
                            void *store);
    void        obs_shutdown(void);
    bool        obs_initialized(void);
    uint32_t    obs_get_version(void);
    const char *obs_get_version_string(void);
    void        obs_set_locale(const char *locale);
    const char *obs_get_locale(void);

    enum obs_video_err obs_reset_video(struct obs_video_info *ovi);
    bool               obs_reset_audio(const struct obs_audio_info *oai);
    bool               obs_get_audio_info(struct obs_audio_info *oai);
    bool               obs_video_active(void);

    void obs_add_module_path(const char *bin, const char *data);
    void obs_load_all_modules(void);
    void obs_post_load_modules(void);

    void obs_add_data_path(const char *path);
    bool obs_remove_data_path(const char *path);
    char *obs_find_data_file(const char *file);

    obs_source_t *obs_get_output_source(uint32_t channel);
    void          obs_set_output_source(uint32_t channel, obs_source_t *source);

    video_t *obs_get_video(void);
    audio_t *obs_get_audio(void);

    signal_handler_t *obs_get_signal_handler(void);
    proc_handler_t   *obs_get_proc_handler(void);

    /* Display / preview rendering ---------------------------------- */
    typedef void (*obs_display_draw_callback_t)(void *param,
                                                uint32_t cx, uint32_t cy);

    obs_display_t *obs_display_create(const struct gs_init_data *graphics_data,
                                      uint32_t background_color);
    void           obs_display_destroy(obs_display_t *display);
    void           obs_display_resize(obs_display_t *display,
                                      uint32_t cx, uint32_t cy);
    void           obs_display_set_background_color(obs_display_t *display,
                                                    uint32_t color);
    void           obs_display_size(obs_display_t *display,
                                    uint32_t *width, uint32_t *height);
    void           obs_display_add_draw_callback(obs_display_t *display,
                                                 obs_display_draw_callback_t draw,
                                                 void *param);
    void           obs_display_remove_draw_callback(obs_display_t *display,
                                                    obs_display_draw_callback_t draw,
                                                    void *param);
    void           obs_display_set_enabled(obs_display_t *display, bool enable);
    bool           obs_display_enabled(obs_display_t *display);

    void obs_render_main_texture(void);

    /* Render a specific source's video (not channel 0) into the current
       render target. Useful for preview panes that need to draw a different
       scene than the on-air program — keep a separate "preview" scene and
       render it via this call so layout switches don't immediately affect
       program output. */
    void obs_source_video_render(obs_source_t *source);

    /* Transition API: ``obs_transition_set`` / ``obs_transition_start``
       are declared in ``_TRANSITIONS`` below. The standard
       ``fade_transition`` from obs-transitions.dll implements a Dissolve. */

    /* graphics ortho/viewport — used inside display draw callbacks */
    void gs_set_viewport(int x, int y, int width, int height);
    void gs_ortho(float left, float right, float top, float bottom,
                  float znear, float zfar);
    void gs_projection_push(void);
    void gs_projection_pop(void);

    /* Properties API ------------------------------------------------- */
    obs_properties_t *obs_source_properties(const obs_source_t *source);
    obs_properties_t *obs_get_source_properties(const char *id);
    obs_properties_t *obs_get_encoder_properties(const char *id);
    obs_properties_t *obs_get_output_properties(const char *id);
    obs_properties_t *obs_get_service_properties(const char *id);
    void              obs_properties_destroy(obs_properties_t *props);

    obs_property_t *obs_properties_first(obs_properties_t *props);
    obs_property_t *obs_properties_get(obs_properties_t *props, const char *name);
    bool            obs_property_next(obs_property_t **p);
    const char     *obs_property_name(obs_property_t *p);
    const char     *obs_property_description(obs_property_t *p);
    int             obs_property_get_type(obs_property_t *p);
    bool            obs_property_visible(obs_property_t *p);
    bool            obs_property_enabled(obs_property_t *p);

    size_t          obs_property_list_item_count(obs_property_t *p);
    const char     *obs_property_list_item_name(obs_property_t *p, size_t idx);
    const char     *obs_property_list_item_string(obs_property_t *p, size_t idx);
    long long       obs_property_list_item_int(obs_property_t *p, size_t idx);
    double          obs_property_list_item_float(obs_property_t *p, size_t idx);
    bool            obs_property_list_item_disabled(obs_property_t *p, size_t idx);
    int             obs_property_list_type(obs_property_t *p);
    int             obs_property_list_format(obs_property_t *p);
"""

# ---------------------------------------------------------------------------
# obs_data_t — settings/configuration
# ---------------------------------------------------------------------------
_DATA = """
    obs_data_t *obs_data_create(void);
    obs_data_t *obs_data_create_from_json(const char *json_string);
    obs_data_t *obs_data_create_from_json_file(const char *json_file);
    void        obs_data_addref(obs_data_t *data);
    void        obs_data_release(obs_data_t *data);

    const char *obs_data_get_json(obs_data_t *data);
    const char *obs_data_get_json_pretty(obs_data_t *data);

    void obs_data_set_string(obs_data_t *data, const char *name, const char *val);
    void obs_data_set_int(obs_data_t *data, const char *name, long long val);
    void obs_data_set_double(obs_data_t *data, const char *name, double val);
    void obs_data_set_bool(obs_data_t *data, const char *name, bool val);
    void obs_data_set_obj(obs_data_t *data, const char *name, obs_data_t *obj);
    void obs_data_set_array(obs_data_t *data, const char *name,
                            obs_data_array_t *array);

    const char      *obs_data_get_string(obs_data_t *data, const char *name);
    long long        obs_data_get_int(obs_data_t *data, const char *name);
    double           obs_data_get_double(obs_data_t *data, const char *name);
    bool             obs_data_get_bool(obs_data_t *data, const char *name);
    obs_data_t      *obs_data_get_obj(obs_data_t *data, const char *name);
    obs_data_array_t*obs_data_get_array(obs_data_t *data, const char *name);

    void obs_data_erase(obs_data_t *data, const char *name);
    void obs_data_clear(obs_data_t *data);

    /* obs_data_array */
    obs_data_array_t *obs_data_array_create(void);
    void              obs_data_array_addref(obs_data_array_t *array);
    void              obs_data_array_release(obs_data_array_t *array);
    size_t            obs_data_array_count(obs_data_array_t *array);
    obs_data_t       *obs_data_array_item(obs_data_array_t *array, size_t idx);
    size_t            obs_data_array_push_back(obs_data_array_t *array,
                                               obs_data_t *obj);
    void              obs_data_array_insert(obs_data_array_t *array, size_t idx,
                                            obs_data_t *obj);
    void              obs_data_array_erase(obs_data_array_t *array, size_t idx);
"""

# ---------------------------------------------------------------------------
# obs_source_t
# ---------------------------------------------------------------------------
_SOURCE = """
    obs_source_t *obs_source_create(const char *id, const char *name,
                                    obs_data_t *settings,
                                    obs_data_t *hotkey_data);
    obs_source_t *obs_source_create_private(const char *id, const char *name,
                                            obs_data_t *settings);
    void          obs_source_release(obs_source_t *source);
    void          obs_source_remove(obs_source_t *source);
    bool          obs_source_removed(const obs_source_t *source);

    /* OBS 32+: obs_*_get_ref() replaces obs_*_addref(). Returns the same
       pointer (now a strong ref the caller MUST release) when the object is
       still alive, or NULL if it was already destroyed / is being destroyed. */
    obs_source_t  *obs_source_get_ref(obs_source_t *source);
    obs_scene_t   *obs_scene_get_ref(obs_scene_t *scene);
    obs_output_t  *obs_output_get_ref(obs_output_t *output);
    obs_encoder_t *obs_encoder_get_ref(obs_encoder_t *encoder);
    obs_service_t *obs_service_get_ref(obs_service_t *service);

    const char *obs_source_get_id(const obs_source_t *source);
    const char *obs_source_get_name(const obs_source_t *source);
    void        obs_source_set_name(obs_source_t *source, const char *name);

    void       obs_source_update(obs_source_t *source, obs_data_t *settings);
    obs_data_t*obs_source_get_settings(obs_source_t *source);

    uint32_t obs_source_get_width(obs_source_t *source);
    uint32_t obs_source_get_height(obs_source_t *source);

    bool obs_source_enabled(const obs_source_t *source);
    void obs_source_set_enabled(obs_source_t *source, bool enabled);

    bool obs_source_muted(const obs_source_t *source);
    void obs_source_set_muted(obs_source_t *source, bool muted);

    float obs_source_get_volume(const obs_source_t *source);
    void  obs_source_set_volume(obs_source_t *source, float volume);

    // Audio monitoring (route a source's audio to the OS speakers).
    // Without these, sources go only to program output (recording /
    // streaming) and are inaudible — confirmed in the libobs PoC
    // when ffmpeg_source produced audio packets but the speakers
    // stayed silent.
    //
    // ``obs_monitoring_type`` enum values:
    //   0 = OBS_MONITORING_TYPE_NONE              (default — silent)
    //   1 = OBS_MONITORING_TYPE_MONITOR_ONLY       (heard, not recorded)
    //   2 = OBS_MONITORING_TYPE_MONITOR_AND_OUTPUT (heard AND recorded)
    void obs_source_set_monitoring_type(obs_source_t *source, int type);
    int  obs_source_get_monitoring_type(const obs_source_t *source);

    bool obs_set_audio_monitoring_device(const char *name, const char *id);
    void obs_get_audio_monitoring_device(const char **name, const char **id);

    signal_handler_t *obs_source_get_signal_handler(const obs_source_t *source);

    obs_source_t *obs_get_source_by_name(const char *name);
    obs_source_t *obs_get_source_by_uuid(const char *uuid);
    const char   *obs_source_get_uuid(const obs_source_t *source);

    uint32_t obs_source_get_output_flags(const obs_source_t *source);
"""

# ---------------------------------------------------------------------------
# obs_scene_t
# ---------------------------------------------------------------------------
_SCENE = """
    obs_scene_t    *obs_scene_create(const char *name);
    obs_scene_t    *obs_scene_create_private(const char *name);
    void            obs_scene_release(obs_scene_t *scene);
    obs_source_t   *obs_scene_get_source(const obs_scene_t *scene);
    obs_scene_t    *obs_scene_from_source(const obs_source_t *source);
    obs_sceneitem_t*obs_scene_find_source(obs_scene_t *scene, const char *name);
    obs_sceneitem_t*obs_scene_add(obs_scene_t *scene, obs_source_t *source);

    void obs_scene_enum_items(obs_scene_t *scene,
                              bool (*callback)(obs_scene_t*, obs_sceneitem_t*,
                                              void*),
                              void *param);

    /* scene item */
    void            obs_sceneitem_addref(obs_sceneitem_t *item);
    void            obs_sceneitem_release(obs_sceneitem_t *item);
    obs_scene_t    *obs_sceneitem_get_scene(const obs_sceneitem_t *item);
    obs_source_t   *obs_sceneitem_get_source(const obs_sceneitem_t *item);

    bool obs_sceneitem_visible(const obs_sceneitem_t *item);
    void obs_sceneitem_set_visible(obs_sceneitem_t *item, bool visible);
    bool obs_sceneitem_locked(const obs_sceneitem_t *item);
    void obs_sceneitem_set_locked(obs_sceneitem_t *item, bool locked);
    void obs_sceneitem_remove(obs_sceneitem_t *item);
    bool obs_sceneitem_is_group(const obs_sceneitem_t *item);

    int  obs_sceneitem_get_order_position(obs_sceneitem_t *item);
    void obs_sceneitem_set_order_position(obs_sceneitem_t *item, int position);

    struct vec2 { float x; float y; };
    void obs_sceneitem_set_pos(obs_sceneitem_t *item, const struct vec2 *pos);
    void obs_sceneitem_get_pos(const obs_sceneitem_t *item, struct vec2 *pos);
    void obs_sceneitem_set_scale(obs_sceneitem_t *item, const struct vec2 *scale);
    void obs_sceneitem_get_scale(const obs_sceneitem_t *item, struct vec2 *scale);
    void obs_sceneitem_set_rot(obs_sceneitem_t *item, float rot);
    float obs_sceneitem_get_rot(const obs_sceneitem_t *item);
"""

# ---------------------------------------------------------------------------
# obs_encoder_t
# ---------------------------------------------------------------------------
_ENCODER = """
    obs_encoder_t *obs_video_encoder_create(const char *id, const char *name,
                                            obs_data_t *settings,
                                            obs_data_t *hotkey_data);
    obs_encoder_t *obs_audio_encoder_create(const char *id, const char *name,
                                            obs_data_t *settings,
                                            size_t mixer_idx,
                                            obs_data_t *hotkey_data);
    void           obs_encoder_release(obs_encoder_t *encoder);

    const char *obs_encoder_get_id(const obs_encoder_t *encoder);
    const char *obs_encoder_get_name(const obs_encoder_t *encoder);
    void        obs_encoder_set_name(obs_encoder_t *encoder, const char *name);

    void        obs_encoder_update(obs_encoder_t *encoder, obs_data_t *settings);
    obs_data_t *obs_encoder_get_settings(obs_encoder_t *encoder);

    void     obs_encoder_set_video(obs_encoder_t *encoder, video_t *video);
    void     obs_encoder_set_audio(obs_encoder_t *encoder, audio_t *audio);
    video_t *obs_encoder_video(const obs_encoder_t *encoder);
    audio_t *obs_encoder_audio(const obs_encoder_t *encoder);

    bool obs_encoder_active(const obs_encoder_t *encoder);

    enum obs_encoder_type obs_encoder_get_type(const obs_encoder_t *encoder);
    const char           *obs_encoder_get_codec(const obs_encoder_t *encoder);
    /* obs_encoder_get_signal_handler removed in OBS 32 — use the
       obs_output's signal handler to track encoder state instead. */
"""

# ---------------------------------------------------------------------------
# obs_service_t
# ---------------------------------------------------------------------------
_SERVICE = """
    obs_service_t *obs_service_create(const char *id, const char *name,
                                      obs_data_t *settings,
                                      obs_data_t *hotkey_data);
    void           obs_service_release(obs_service_t *service);

    const char *obs_service_get_id(const obs_service_t *service);
    const char *obs_service_get_name(const obs_service_t *service);

    void        obs_service_update(obs_service_t *service, obs_data_t *settings);
    obs_data_t *obs_service_get_settings(const obs_service_t *service);

    /* obs_service_get_url/key/username/password were removed in OBS 32 —
       read these out of obs_service_get_settings() as obs_data fields
       (key names "server", "key", "username", "password"). */
"""

# ---------------------------------------------------------------------------
# obs_output_t
# ---------------------------------------------------------------------------
_OUTPUT = """
    obs_output_t *obs_output_create(const char *id, const char *name,
                                    obs_data_t *settings,
                                    obs_data_t *hotkey_data);
    void          obs_output_release(obs_output_t *output);

    const char *obs_output_get_id(const obs_output_t *output);
    const char *obs_output_get_name(const obs_output_t *output);
    /* obs_output_set_name was made private in OBS 32 — set the name when
       calling obs_output_create instead. */

    bool obs_output_start(obs_output_t *output);
    void obs_output_stop(obs_output_t *output);
    void obs_output_force_stop(obs_output_t *output);
    bool obs_output_active(const obs_output_t *output);
    bool obs_output_paused(const obs_output_t *output);
    void obs_output_pause(obs_output_t *output, bool pause);

    void           obs_output_set_video_encoder(obs_output_t *output,
                                                obs_encoder_t *encoder);
    void           obs_output_set_audio_encoder(obs_output_t *output,
                                                obs_encoder_t *encoder,
                                                size_t idx);
    obs_encoder_t *obs_output_get_video_encoder(const obs_output_t *output);
    obs_encoder_t *obs_output_get_audio_encoder(const obs_output_t *output,
                                                size_t idx);

    void           obs_output_set_service(obs_output_t *output,
                                          obs_service_t *service);
    obs_service_t *obs_output_get_service(const obs_output_t *output);

    void        obs_output_update(obs_output_t *output, obs_data_t *settings);
    obs_data_t *obs_output_get_settings(const obs_output_t *output);

    signal_handler_t *obs_output_get_signal_handler(const obs_output_t *output);

    const char *obs_output_get_last_error(obs_output_t *output);

    uint64_t obs_output_get_total_bytes(const obs_output_t *output);
    int      obs_output_get_frames_dropped(const obs_output_t *output);
    int      obs_output_get_total_frames(const obs_output_t *output);

    double obs_output_get_congestion(obs_output_t *output);
    int    obs_output_get_connect_time_ms(obs_output_t *output);
"""

# ---------------------------------------------------------------------------
# Signal handler
# ---------------------------------------------------------------------------
_SIGNALS = """
    signal_handler_t *signal_handler_create(void);
    void              signal_handler_destroy(signal_handler_t *handler);
    void  signal_handler_connect(signal_handler_t *handler, const char *signal,
                                 signal_callback_t callback, void *data);
    void  signal_handler_disconnect(signal_handler_t *handler, const char *signal,
                                    signal_callback_t callback, void *data);

    /* The typed calldata getters (calldata_get_bool / _int / _float /
       _ptr) are static-inline in the libobs header and aren't exported.
       They all call calldata_get_data() with the right size. The string
       variant IS exported separately (it returns a const char* without a
       buffer-size dance). calldata_get_data + calldata_set_data are
       declared by AUTO_DECLS. */
    bool calldata_get_string(const calldata_t *data, const char *name,
                              const char **out);
"""

# ---------------------------------------------------------------------------
# Filters (filters are sources with filter-type ids; these are the
# parent/child relationship calls)
# ---------------------------------------------------------------------------
_FILTERS = """
    void          obs_source_filter_add(obs_source_t *source, obs_source_t *filter);
    void          obs_source_filter_remove(obs_source_t *source, obs_source_t *filter);
    size_t        obs_source_filter_count(const obs_source_t *source);
    obs_source_t *obs_source_get_filter_by_name(obs_source_t *source,
                                                const char *name);
    size_t        obs_source_filter_get_index(obs_source_t *source,
                                              obs_source_t *filter);
    void          obs_source_filter_set_index(obs_source_t *source,
                                              obs_source_t *filter, size_t idx);
    obs_source_t *obs_filter_get_parent(const obs_source_t *filter);
    obs_source_t *obs_filter_get_target(const obs_source_t *filter);

    typedef void (*obs_source_enum_filters_cb_t)(obs_source_t *parent,
                                                 obs_source_t *child,
                                                 void *param);
    void obs_source_enum_filters(obs_source_t *source,
                                 obs_source_enum_filters_cb_t cb, void *param);
"""

# ---------------------------------------------------------------------------
# Transitions
# ---------------------------------------------------------------------------
_TRANSITIONS = """
    enum obs_transition_mode {
        OBS_TRANSITION_MODE_AUTO   = 0,
        OBS_TRANSITION_MODE_MANUAL = 1
    };

    bool          obs_transition_start(obs_source_t *transition,
                                       enum obs_transition_mode mode,
                                       uint32_t duration_ms,
                                       obs_source_t *dest);
    void          obs_transition_clear(obs_source_t *transition);
    void          obs_transition_set(obs_source_t *transition, obs_source_t *src);
    obs_source_t *obs_transition_get_source(const obs_source_t *transition, int channel);
    obs_source_t *obs_transition_get_active_source(const obs_source_t *transition);

    void  obs_transition_set_size(obs_source_t *transition, uint32_t cx, uint32_t cy);
    void  obs_transition_get_size(const obs_source_t *transition,
                                  uint32_t *cx, uint32_t *cy);
    float obs_transition_get_time(obs_source_t *transition);

    obs_source_t *obs_get_transition_by_name(const char *name);
    obs_source_t *obs_get_transition_by_uuid(const char *uuid);
"""

# ---------------------------------------------------------------------------
# Hotkeys
# ---------------------------------------------------------------------------
_HOTKEYS = """
    /* Registration ------------------------------------------------- */
    obs_hotkey_id obs_hotkey_register_frontend(const char *name,
                                               const char *description,
                                               obs_hotkey_func func, void *data);
    obs_hotkey_id obs_hotkey_register_source(obs_source_t *source,
                                             const char *name,
                                             const char *description,
                                             obs_hotkey_func func, void *data);
    void          obs_hotkey_unregister(obs_hotkey_id id);

    /* Inspection --------------------------------------------------- */
    const char *obs_hotkey_get_name(const obs_hotkey_t *hotkey);
    const char *obs_hotkey_get_description(const obs_hotkey_t *hotkey);
    obs_hotkey_id obs_hotkey_get_id(const obs_hotkey_t *hotkey);

    /* Triggering / event injection --------------------------------- */
    void obs_hotkey_trigger_routed_callback(obs_hotkey_id id, bool pressed);
    void obs_hotkey_inject_event(obs_key_combination_t hotkey, bool pressed);
    void obs_hotkey_enable_callback_rerouting(bool enable);
    void obs_hotkey_enable_background_press(bool enable);

    /* Persistence -------------------------------------------------- */
    obs_data_array_t *obs_hotkey_save(obs_hotkey_id id);
    void              obs_hotkey_load(obs_hotkey_id id, obs_data_array_t *data);

    /* Key code helpers --------------------------------------------- */
    obs_key_t obs_key_from_name(const char *name);
    const char *obs_key_to_name(obs_key_t key);

    /* Enumeration */
    typedef bool (*obs_hotkey_enum_func)(void *data, obs_hotkey_id id,
                                          obs_hotkey_t *key);
    void obs_enum_hotkeys(obs_hotkey_enum_func func, void *data);
"""

# ---------------------------------------------------------------------------
# Volume meter
# ---------------------------------------------------------------------------
_VOLMETER = """
    enum obs_peak_meter_type {
        SAMPLE_PEAK_METER = 0,
        TRUE_PEAK_METER   = 1
    };

    obs_volmeter_t *obs_volmeter_create(enum obs_peak_meter_type peak_meter_type);
    void            obs_volmeter_destroy(obs_volmeter_t *volmeter);
    bool            obs_volmeter_attach_source(obs_volmeter_t *volmeter,
                                               obs_source_t *source);
    void            obs_volmeter_detach_source(obs_volmeter_t *volmeter);
    void            obs_volmeter_set_peak_meter_type(obs_volmeter_t *volmeter,
                                                     enum obs_peak_meter_type type);
    int             obs_volmeter_get_nr_channels(obs_volmeter_t *volmeter);
    void            obs_volmeter_add_callback(obs_volmeter_t *volmeter,
                                              obs_volmeter_updated_t callback,
                                              void *param);
    void            obs_volmeter_remove_callback(obs_volmeter_t *volmeter,
                                                 obs_volmeter_updated_t callback,
                                                 void *param);
"""

# ---------------------------------------------------------------------------
# Fader
# ---------------------------------------------------------------------------
_FADER = """
    enum obs_fader_type {
        OBS_FADER_CUBIC = 0,
        OBS_FADER_IEC   = 1,
        OBS_FADER_LOG   = 2
    };

    obs_fader_t *obs_fader_create(enum obs_fader_type type);
    void         obs_fader_destroy(obs_fader_t *fader);
    bool         obs_fader_set_db(obs_fader_t *fader, float db);
    float        obs_fader_get_db(const obs_fader_t *fader);
    bool         obs_fader_set_deflection(obs_fader_t *fader, float def);
    float        obs_fader_get_deflection(const obs_fader_t *fader);
    bool         obs_fader_set_mul(obs_fader_t *fader, float mul);
    float        obs_fader_get_mul(const obs_fader_t *fader);
    bool         obs_fader_attach_source(obs_fader_t *fader, obs_source_t *source);
    void         obs_fader_detach_source(obs_fader_t *fader);
    float        obs_fader_db_to_def(obs_fader_t *fader, float db);
    void         obs_fader_add_callback(obs_fader_t *fader,
                                        obs_fader_changed_t callback, void *param);
    void         obs_fader_remove_callback(obs_fader_t *fader,
                                           obs_fader_changed_t callback,
                                           void *param);
"""

# ---------------------------------------------------------------------------
# Enumeration APIs
# ---------------------------------------------------------------------------
_ENUMERATE = """
    void obs_enum_sources(obs_enum_source_cb_t cb, void *data);
    void obs_enum_scenes(obs_enum_source_cb_t cb, void *data);
    void obs_enum_all_sources(obs_enum_source_cb_t cb, void *data);

    /* Type-id enumerators — return false when idx is out of range */
    bool obs_enum_source_types(size_t idx, const char **id);
    bool obs_enum_input_types(size_t idx, const char **id);
    bool obs_enum_input_types2(size_t idx, const char **id,
                                const char **unversioned_id);
    bool obs_enum_filter_types(size_t idx, const char **id);
    bool obs_enum_transition_types(size_t idx, const char **id);
    bool obs_enum_encoder_types(size_t idx, const char **id);
    bool obs_enum_output_types(size_t idx, const char **id);
    bool obs_enum_service_types(size_t idx, const char **id);

    const char *obs_source_get_display_name(const char *id);
    const char *obs_output_get_display_name(const char *id);
    const char *obs_encoder_get_display_name(const char *id);
    const char *obs_service_get_display_name(const char *id);

    /* Type-defaults */
    obs_data_t *obs_get_source_defaults(const char *id);
    obs_data_t *obs_encoder_defaults(const char *id);
    obs_data_t *obs_service_defaults(const char *id);
    /* obs_output_defaults declared by AUTO_DECLS */

    /* Audio monitoring — note: obs_set/get_audio_monitoring_device and
       obs_source_set/get_monitoring_type are declared in the SOURCE block. */
    void obs_enum_audio_monitoring_devices(obs_enum_audio_devices_cb_t cb,
                                           void *data);
    bool obs_audio_monitoring_available(void);
    void obs_reset_audio_monitoring(void);
    void obs_source_set_audio_mixers(obs_source_t *source, uint32_t mixers);
    uint32_t obs_source_get_audio_mixers(const obs_source_t *source);
    bool obs_source_audio_active(const obs_source_t *source);
    void obs_source_set_audio_active(obs_source_t *source, bool active);

    /* Per-source audio fine controls */
    void  obs_source_set_balance_value(obs_source_t *source, float balance);
    float obs_source_get_balance_value(const obs_source_t *source);
    void   obs_source_set_sync_offset(obs_source_t *source, int64_t offset);
    int64_t obs_source_get_sync_offset(const obs_source_t *source);
    int    obs_source_get_speaker_layout(obs_source_t *source);
    /* (obs_get_audio_info already declared in the CORE block) */
"""

# ---------------------------------------------------------------------------
# Raw video / audio capture callbacks (NumPy-friendly access to frames)
# ---------------------------------------------------------------------------
_RAW_CALLBACKS = """
    struct audio_data {
        uint8_t  *data[8];      /* MAX_AV_PLANES */
        uint32_t  frames;
        uint64_t  timestamp;
    };

    struct video_data {
        uint8_t  *data[8];
        uint32_t  linesize[8];
        uint64_t  timestamp;
    };

    /* Subset of video_scale_info used by raw_video_callback2 to request a
       specific format/colorspace/range without changing the global output. */
    struct video_scale_info {
        enum video_format     format;
        uint32_t              width;
        uint32_t              height;
        enum video_range_type range;
        enum video_colorspace colorspace;
    };

    /* Per-source audio capture */
    typedef void (*obs_source_audio_capture_t)(void *param,
                                               obs_source_t *source,
                                               const struct audio_data *audio_data,
                                               bool muted);
    void obs_source_add_audio_capture_callback(obs_source_t *source,
                                               obs_source_audio_capture_t cb,
                                               void *param);
    void obs_source_remove_audio_capture_callback(obs_source_t *source,
                                                  obs_source_audio_capture_t cb,
                                                  void *param);

    /* Global raw audio (post-mix) */
    typedef void (*audio_output_callback_t)(void *param,
                                            size_t mix_idx,
                                            struct audio_data *data);
    void obs_add_raw_audio_callback(size_t mix_idx,
                                    const struct audio_data *conversion,
                                    audio_output_callback_t callback,
                                    void *param);
    void obs_remove_raw_audio_callback(size_t mix_idx,
                                       audio_output_callback_t callback,
                                       void *param);

    /* Global raw video (post-render) */
    typedef void (*raw_video_callback_t)(void *param, struct video_data *frame);
    void obs_add_raw_video_callback(const struct video_scale_info *conversion,
                                    raw_video_callback_t callback,
                                    void *param);
    void obs_remove_raw_video_callback(raw_video_callback_t callback,
                                       void *param);

    /* Per-frame render hooks */
    typedef void (*obs_render_callback_t)(void *param, uint32_t cx, uint32_t cy);
    void obs_add_main_render_callback(obs_render_callback_t cb, void *param);
    void obs_remove_main_render_callback(obs_render_callback_t cb, void *param);
    typedef void (*obs_tick_callback_t)(void *param, float seconds);
    void obs_add_tick_callback(obs_tick_callback_t cb, void *param);
    void obs_remove_tick_callback(obs_tick_callback_t cb, void *param);
"""

# ---------------------------------------------------------------------------
# Scene item full transform (alignment, bounds, blending, crop, group ops)
# ---------------------------------------------------------------------------
_SCENEITEM_TRANSFORM = """
    enum obs_bounds_type {
        OBS_BOUNDS_NONE          = 0,
        OBS_BOUNDS_STRETCH       = 1,
        OBS_BOUNDS_SCALE_INNER   = 2,
        OBS_BOUNDS_SCALE_OUTER   = 3,
        OBS_BOUNDS_SCALE_TO_WIDTH= 4,
        OBS_BOUNDS_SCALE_TO_HEIGHT=5,
        OBS_BOUNDS_MAX_ONLY      = 6
    };

    enum obs_blending_method {
        OBS_BLEND_METHOD_DEFAULT    = 0,
        OBS_BLEND_METHOD_SRGB_OFF   = 1
    };

    enum obs_blending_type {
        OBS_BLEND_NORMAL     = 0,
        OBS_BLEND_ADDITIVE   = 1,
        OBS_BLEND_SUBTRACT   = 2,
        OBS_BLEND_SCREEN     = 3,
        OBS_BLEND_MULTIPLY   = 4,
        OBS_BLEND_LIGHTEN    = 5,
        OBS_BLEND_DARKEN     = 6
    };

    /* Common alignment flags (matches OBS_ALIGN_* in libobs) */
    /* center=0, left=1, right=2, top=4, bottom=8 — combine with OR */

    struct obs_sceneitem_crop {
        int left;
        int top;
        int right;
        int bottom;
    };

    /* Full transform info struct */
    struct obs_transform_info {
        struct vec2            pos;
        float                  rot;
        struct vec2            scale;
        uint32_t               alignment;

        enum obs_bounds_type   bounds_type;
        uint32_t               bounds_alignment;
        struct vec2            bounds;
        bool                   crop_to_bounds;
        struct obs_sceneitem_crop bounds_crop;
    };

    /* Sceneitem getters/setters we still need */
    uint32_t obs_sceneitem_get_alignment(const obs_sceneitem_t *item);
    void     obs_sceneitem_set_alignment(obs_sceneitem_t *item, uint32_t alignment);

    void                  obs_sceneitem_set_bounds_type(obs_sceneitem_t *item,
                                                        enum obs_bounds_type type);
    enum obs_bounds_type  obs_sceneitem_get_bounds_type(const obs_sceneitem_t *item);
    void     obs_sceneitem_set_bounds_alignment(obs_sceneitem_t *item, uint32_t alignment);
    uint32_t obs_sceneitem_get_bounds_alignment(const obs_sceneitem_t *item);
    void     obs_sceneitem_set_bounds(obs_sceneitem_t *item, const struct vec2 *bounds);
    void     obs_sceneitem_get_bounds(const obs_sceneitem_t *item, struct vec2 *bounds);
    void     obs_sceneitem_set_bounds_crop(obs_sceneitem_t *item,
                                           const struct obs_sceneitem_crop *crop);
    void     obs_sceneitem_get_bounds_crop(const obs_sceneitem_t *item,
                                           struct obs_sceneitem_crop *crop);

    void  obs_sceneitem_set_crop(obs_sceneitem_t *item,
                                 const struct obs_sceneitem_crop *crop);
    void  obs_sceneitem_get_crop(const obs_sceneitem_t *item,
                                 struct obs_sceneitem_crop *crop);

    enum obs_blending_method obs_sceneitem_get_blending_method(const obs_sceneitem_t *item);
    void obs_sceneitem_set_blending_method(obs_sceneitem_t *item,
                                           enum obs_blending_method method);
    enum obs_blending_type   obs_sceneitem_get_blending_mode(const obs_sceneitem_t *item);
    void obs_sceneitem_set_blending_mode(obs_sceneitem_t *item,
                                         enum obs_blending_type type);

    /* Bulk transform info — read/write everything in one call */
    void obs_sceneitem_set_info2(obs_sceneitem_t *item,
                                 const struct obs_transform_info *info);
    void obs_sceneitem_get_info2(const obs_sceneitem_t *item,
                                 struct obs_transform_info *info);

    /* Defer transform updates to coalesce many edits */
    void obs_sceneitem_defer_update_begin(obs_sceneitem_t *item);
    void obs_sceneitem_defer_update_end(obs_sceneitem_t *item);
    void obs_sceneitem_force_update_transform(obs_sceneitem_t *item);

    obs_data_t *obs_sceneitem_get_private_settings(obs_sceneitem_t *item);

    /* Groups (obs_sceneitem_is_group already declared in SCENE block) */
    obs_sceneitem_t *obs_scene_add_group(obs_scene_t *scene, const char *name);
    obs_sceneitem_t *obs_scene_insert_group(obs_scene_t *scene, const char *name,
                                            obs_sceneitem_t **items, size_t count);
    obs_scene_t     *obs_sceneitem_group_get_scene(const obs_sceneitem_t *group);
    void             obs_sceneitem_group_add_item(obs_sceneitem_t *group,
                                                  obs_sceneitem_t *item);
    void             obs_sceneitem_group_remove_item(obs_sceneitem_t *group,
                                                     obs_sceneitem_t *item);
    obs_scene_t     *obs_scene_duplicate(obs_scene_t *scene, const char *name,
                                         int dup_type);
"""

# ---------------------------------------------------------------------------
# OBS data — full coverage (arrays, defaults, iteration, JSON file save)
# ---------------------------------------------------------------------------
_DATA_FULL = """
    /* Iteration */
    typedef struct obs_data_item obs_data_item_t;
    obs_data_item_t *obs_data_first(obs_data_t *data);
    bool             obs_data_item_next(obs_data_item_t **item);
    void             obs_data_item_release(obs_data_item_t **item);
    const char      *obs_data_item_get_name(const obs_data_item_t *item);
    int              obs_data_item_gettype(const obs_data_item_t *item);

    /* Type query — call obs_data_item_gettype on the result of obs_data_first
       to walk types. obs_data_get_type(data, name) was removed in OBS 32. */

    /* Defaults */
    void obs_data_set_default_string(obs_data_t *data, const char *name, const char *val);
    void obs_data_set_default_int(obs_data_t *data, const char *name, long long val);
    void obs_data_set_default_double(obs_data_t *data, const char *name, double val);
    void obs_data_set_default_bool(obs_data_t *data, const char *name, bool val);
    void obs_data_set_default_obj(obs_data_t *data, const char *name, obs_data_t *obj);

    const char *obs_data_get_default_string(obs_data_t *data, const char *name);
    long long   obs_data_get_default_int(obs_data_t *data, const char *name);
    double      obs_data_get_default_double(obs_data_t *data, const char *name);
    bool        obs_data_get_default_bool(obs_data_t *data, const char *name);
    obs_data_t *obs_data_get_default_obj(obs_data_t *data, const char *name);

    bool obs_data_has_default_value(obs_data_t *data, const char *name);
    bool obs_data_has_user_value(obs_data_t *data, const char *name);
    void obs_data_unset_user_value(obs_data_t *data, const char *name);
    void obs_data_unset_default_value(obs_data_t *data, const char *name);

    /* Save to JSON file */
    bool obs_data_save_json(obs_data_t *data, const char *file);
    bool obs_data_save_json_safe(obs_data_t *data, const char *file,
                                 const char *temp_ext, const char *backup_ext);

    /* Apply: merge `apply_data` into `target` */
    void obs_data_apply(obs_data_t *target, obs_data_t *apply_data);
"""

# ---------------------------------------------------------------------------
# Property accessors — read INT/FLOAT/TEXT/PATH ranges and types
# ---------------------------------------------------------------------------
_PROPERTY_ACCESSORS = """
    long long obs_property_int_min(obs_property_t *p);
    long long obs_property_int_max(obs_property_t *p);
    long long obs_property_int_step(obs_property_t *p);
    int       obs_property_int_type(obs_property_t *p);    /* 0 scroller, 1 slider */
    const char *obs_property_int_suffix(obs_property_t *p);

    double obs_property_float_min(obs_property_t *p);
    double obs_property_float_max(obs_property_t *p);
    double obs_property_float_step(obs_property_t *p);
    int    obs_property_float_type(obs_property_t *p);
    const char *obs_property_float_suffix(obs_property_t *p);

    int obs_property_text_type(obs_property_t *p);   /* 0 default, 1 password, 2 multiline, 3 info */
    int obs_property_text_info_type(obs_property_t *p);
    bool obs_property_text_info_word_wrap(obs_property_t *p);
    int obs_property_text_monospace(obs_property_t *p);

    int obs_property_path_type(obs_property_t *p);     /* 0 file, 1 directory, 2 file_save */
    const char *obs_property_path_filter(obs_property_t *p);
    const char *obs_property_path_default_path(obs_property_t *p);

    /* obs_property_list_type/format already declared in PROPERTIES block */

    bool obs_property_modified(obs_property_t *p, obs_data_t *settings);
    const char *obs_property_long_description(obs_property_t *p);
"""

# ---------------------------------------------------------------------------
# Source state / media / saved settings
# ---------------------------------------------------------------------------
_SOURCE_EXTRAS = """
    /* Active / showing state — incremented per scene the source is in */
    bool obs_source_active(const obs_source_t *source);
    bool obs_source_showing(const obs_source_t *source);
    void obs_source_inc_showing(obs_source_t *source);
    void obs_source_dec_showing(obs_source_t *source);
    void obs_source_inc_active(obs_source_t *source);
    void obs_source_dec_active(obs_source_t *source);

    /* Deinterlace */
    int  obs_source_get_deinterlace_mode(const obs_source_t *source);
    void obs_source_set_deinterlace_mode(obs_source_t *source, int mode);
    int  obs_source_get_deinterlace_field_order(const obs_source_t *source);
    void obs_source_set_deinterlace_field_order(obs_source_t *source, int order);

    /* Icon (for picker UIs) */
    int obs_source_get_icon_type(const char *id);

    /* Media controls — for ffmpeg_source, vlc_source */
    void     obs_source_media_play_pause(obs_source_t *source, bool pause);
    void     obs_source_media_restart(obs_source_t *source);
    void     obs_source_media_stop(obs_source_t *source);
    void     obs_source_media_next(obs_source_t *source);
    void     obs_source_media_previous(obs_source_t *source);
    int64_t  obs_source_media_get_duration(obs_source_t *source);
    int64_t  obs_source_media_get_time(obs_source_t *source);
    void     obs_source_media_set_time(obs_source_t *source, int64_t ms);
    int      obs_source_media_get_state(obs_source_t *source);

    /* Private settings (per-source storage that's not in the public settings) */
    obs_data_t *obs_source_get_private_settings(obs_source_t *source);

    /* Save/load — used for persisting to JSON */
    obs_data_t *obs_save_source(obs_source_t *source);
    obs_source_t *obs_load_source(obs_data_t *data);
    obs_source_t *obs_load_private_source(obs_data_t *data);
    obs_data_array_t *obs_save_sources(void);
    obs_data_array_t *obs_save_sources_filtered(bool (*cb)(void *data, obs_source_t *source),
                                                 void *data);

    typedef void (*obs_load_source_cb)(void *private_data, obs_source_t *source);
    void obs_load_sources(obs_data_array_t *array,
                          obs_load_source_cb cb, void *private_data);
"""

# ---------------------------------------------------------------------------
# Output extras — delay, mixers, packet callbacks, reconnect
# ---------------------------------------------------------------------------
_OUTPUT_EXTRAS = """
    /* Mixer track selection (which audio mixers feed this output) */
    void     obs_output_set_mixer(obs_output_t *output, size_t mixer_idx);
    size_t   obs_output_get_mixer(const obs_output_t *output);
    void     obs_output_set_mixers(obs_output_t *output, size_t mixers);
    size_t   obs_output_get_mixers(const obs_output_t *output);

    /* Delay (for delayed broadcasts) */
    void     obs_output_set_delay(obs_output_t *output, uint32_t delay_sec,
                                  uint32_t flags);
    uint32_t obs_output_get_delay(const obs_output_t *output);
    uint32_t obs_output_get_active_delay(const obs_output_t *output);

    /* Reconnect settings (for streaming outputs) */
    void obs_output_set_reconnect_settings(obs_output_t *output, int retry_count,
                                            int retry_sec);
    bool obs_output_reconnecting(const obs_output_t *output);

    /* Capabilities */
    bool     obs_output_can_pause(const obs_output_t *output);
    uint32_t obs_output_get_flags(const obs_output_t *output);

    /* Packet callbacks — get encoded packets as they come out of the encoder */
    struct encoder_packet {
        uint8_t *data;
        size_t   size;
        int64_t  pts;
        int64_t  dts;
        int32_t  timebase_num;
        int32_t  timebase_den;
        int      type;        /* encoder_packet_type */
        bool     keyframe;
        int64_t  dts_usec;
        int64_t  sys_dts_usec;
        int      priority;
        int      drop_priority;
        size_t   track_idx;
        obs_encoder_t *encoder;
    };
    typedef void (*obs_output_packet_cb_t)(void *param,
                                           struct encoder_packet *packet);
    void obs_output_add_packet_callback(obs_output_t *output,
                                        obs_output_packet_cb_t cb, void *param);
    void obs_output_remove_packet_callback(obs_output_t *output,
                                           obs_output_packet_cb_t cb, void *param);
"""

# ---------------------------------------------------------------------------
# Encoder ROI (region-of-interest quality hints)
# ---------------------------------------------------------------------------
_ENCODER_ROI = """
    struct obs_encoder_roi {
        uint32_t left;
        uint32_t top;
        uint32_t right;
        uint32_t bottom;
        float    priority;   /* > 0 = better quality, < 0 = worse */
    };

    bool     obs_encoder_add_roi(obs_encoder_t *encoder,
                                 const struct obs_encoder_roi *roi);
    void     obs_encoder_clear_roi(obs_encoder_t *encoder);
    typedef void (*obs_encoder_roi_cb_t)(void *param,
                                          struct obs_encoder_roi *roi);
    void     obs_encoder_enum_roi(obs_encoder_t *encoder,
                                  obs_encoder_roi_cb_t cb, void *param);
    bool     obs_encoder_has_roi(const obs_encoder_t *encoder);
    uint32_t obs_encoder_get_roi_increment(const obs_encoder_t *encoder);
"""

# ---------------------------------------------------------------------------
# Recursive source enumeration (walk active children of a source)
# ---------------------------------------------------------------------------
_SOURCE_ENUM = """
    typedef void (*obs_source_enum_proc_t)(obs_source_t *parent,
                                            obs_source_t *child, void *param);
    void obs_source_enum_active_sources(obs_source_t *source,
                                        obs_source_enum_proc_t cb, void *param);
    void obs_source_enum_active_tree(obs_source_t *source,
                                     obs_source_enum_proc_t cb, void *param);
    void obs_source_enum_full_tree(obs_source_t *source,
                                   obs_source_enum_proc_t cb, void *param);
"""

# ---------------------------------------------------------------------------
# Video timing / HDR
# ---------------------------------------------------------------------------
_VIDEO_EXTRAS = """
    /* Already-rendered frame timing */
    uint64_t obs_get_video_frame_time(void);
    bool     obs_get_video_info(struct obs_video_info *ovi);
    float    obs_get_video_hdr_nominal_peak_level(void);
    float    obs_get_video_sdr_white_level(void);
    void     obs_set_video_levels(float sdr_white, float hdr_nominal_peak);
"""

# ---------------------------------------------------------------------------
# Filter copy / move
# ---------------------------------------------------------------------------
_FILTER_COPY = """
    void obs_source_copy_filters(obs_source_t *dst, obs_source_t *src);
    bool obs_source_copy_single_filter(obs_source_t *dst, obs_source_t *filter);
    obs_data_array_t *obs_source_backup_filters(obs_source_t *source);
    void obs_source_restore_filters(obs_source_t *source, obs_data_array_t *array);
"""

# Concatenated in load order

# Concatenated in load order
try:
    from ._declarations_auto import PREAMBLE, AUTO_DECLS, STUB_DECLS
except ImportError:
    PREAMBLE = ""
    AUTO_DECLS = ""
    STUB_DECLS = ""


# ---------------------------------------------------------------------------
# Audio resampler — libobs's sample-rate / format / channel-layout converter.
# Usable standalone (no obs_startup needed).
# ---------------------------------------------------------------------------
_AUDIO_RESAMPLER = """
    /* audio_resampler_t typedef'd by _declarations_auto.py.
       Add only the enum, struct, and function signatures here. */
    enum audio_format {
        AUDIO_FORMAT_UNKNOWN        = 0,
        AUDIO_FORMAT_U8BIT          = 1,
        AUDIO_FORMAT_16BIT          = 2,
        AUDIO_FORMAT_32BIT          = 3,
        AUDIO_FORMAT_FLOAT          = 4,
        AUDIO_FORMAT_U8BIT_PLANAR   = 5,
        AUDIO_FORMAT_16BIT_PLANAR   = 6,
        AUDIO_FORMAT_32BIT_PLANAR   = 7,
        AUDIO_FORMAT_FLOAT_PLANAR   = 8
    };

    struct resample_info {
        uint32_t            samples_per_sec;
        enum audio_format   format;
        enum speaker_layout speakers;
    };

    audio_resampler_t *audio_resampler_create(
        const struct resample_info *dst,
        const struct resample_info *src);
    void audio_resampler_destroy(audio_resampler_t *resampler);

    /* output[] is filled in-place with pointers to the resampler's internal
       buffer; the caller must NOT free what it points to (libobs owns the
       memory and reuses it on the next call). *out_frames is set to the
       actual frame count written. */
    bool audio_resampler_resample(audio_resampler_t *resampler,
            uint8_t **output,
            uint32_t *out_frames,
            uint64_t *ts_offset,
            const uint8_t * const *input,
            uint32_t in_frames);
"""

# ---------------------------------------------------------------------------
# Media remuxer — lossless container conversion (e.g. MKV ↔ MP4) without
# decoding or re-encoding. Independent of obs lifecycle.
# ---------------------------------------------------------------------------
_MEDIA_REMUX = """
    /* media_remux_job_t typedef'd by _declarations_auto.py. */
    typedef bool (*media_remux_progress_cb_t)(void *data, float percent);

    bool media_remux_job_create(media_remux_job_t *job,
                                 const char *in_filename,
                                 const char *out_filename);
    bool media_remux_job_process(media_remux_job_t job,
                                  media_remux_progress_cb_t callback,
                                  void *data);
    void media_remux_job_destroy(media_remux_job_t job);
"""


ALL_DECLS = "\n".join([_COMMON, _ENUMS, _STRUCTS, _CORE, _DATA, _SOURCE, _SCENE,
                       _ENCODER, _SERVICE, _OUTPUT, _SIGNALS,
                       _FILTERS, _TRANSITIONS, _HOTKEYS, _VOLMETER, _FADER,
                       _ENUMERATE,
                       _RAW_CALLBACKS, _SCENEITEM_TRANSFORM, _DATA_FULL,
                       _PROPERTY_ACCESSORS, _SOURCE_EXTRAS, _OUTPUT_EXTRAS,
                       _ENCODER_ROI, _SOURCE_ENUM, _VIDEO_EXTRAS, _FILTER_COPY,
                       PREAMBLE,    # Opaque typedefs for auto-extracted decls
                       AUTO_DECLS,
                       STUB_DECLS,
                       # Must come after AUTO_DECLS — uses its typedefs
                       _AUDIO_RESAMPLER, _MEDIA_REMUX])
