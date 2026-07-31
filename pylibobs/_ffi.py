"""
Single cffi FFI instance shared across pylibobs.

The library is loaded lazily on first access so that import-time errors
(e.g. libobs not found) are deferred until actually used.
"""

from __future__ import annotations

import threading
import weakref
from cffi import FFI

from ._declarations import ALL_DECLS

ffi = FFI()
ffi.cdef(ALL_DECLS)

_lib_lock = threading.Lock()
_lib: object | None = None  # cffi lib handle
_alive: bool = False   # True once obs_startup succeeded; reset by obs_shutdown

# Registry of all live Python wrappers that own libobs references.
# Used to release them in the correct order before obs_shutdown().
# WeakSet so we don't extend the lifetime of wrappers the user has dropped.
_wrappers: "weakref.WeakSet[object]" = weakref.WeakSet()
_wrappers_lock = threading.Lock()


def get_lib():
    """Return the loaded cffi library handle, loading it on first call."""
    global _lib
    if _lib is None:
        with _lib_lock:
            if _lib is None:
                from ._lib import find_libobs, prepare_dll_search_path
                path = find_libobs()
                prepare_dll_search_path(path)
                _lib = ffi.dlopen(path)
    return _lib


def mark_alive() -> None:
    global _alive
    _alive = True


def mark_dead() -> None:
    global _alive
    _alive = False


def is_alive() -> bool:
    return _alive


def register_wrapper(obj) -> None:
    """Register a libobs wrapper so it can be released before shutdown.

    Safe to call from any wrapper __init__. Wrappers must expose `release()`.
    """
    with _wrappers_lock:
        _wrappers.add(obj)


def release_all_wrappers() -> None:
    """Release every live wrapper's libobs reference.

    Called by OBSContext.shutdown() BEFORE obs_shutdown(), so libobs sees
    refcount=0 on everything we created and can clean up cleanly.

    Order matters: releasing a Scene cascades and frees its SceneItems and
    Sources inside libobs. If we then call obs_sceneitem_release on freed
    memory, we segfault. So we release in strict dependency order:

        Output  →  Encoder  →  Service  →  SceneItem  →  Source  →  Scene

    Wrappers' Python objects remain alive (user may still hold them); their
    `_ptr` is set to ffi.NULL so subsequent operations no-op.
    """
    # Lazy imports — these modules import from _ffi, so we can't import at top.
    from .output  import Output
    from .encoder import VideoEncoder, AudioEncoder
    from .service import Service
    from .scene   import Scene, SceneItem
    from .source  import Source
    from .display import Display
    from .view    import View
    from .filters import Filter
    from .transitions import Transition
    from .audio_mixer import VolumeMeter, Fader
    from .hotkeys import Hotkey

    # Higher = release earlier. Anything unknown gets sorted last.
    # Hotkeys/Volmeter/Fader come BEFORE sources because they reference them.
    # Filters & Transitions are technically Sources (subclass), but they're
    # safe to release in Source's slot since they share that release path.
    _ORDER: dict[type, int] = {
        Display:       0,  # destroy displays first so the gfx ctx is idle
        Output:        1,
        View:          2,  # after Output (its video_t feeds outputs), before sources
        VideoEncoder:  2,
        AudioEncoder:  2,
        Service:       3,
        Hotkey:        4,
        VolumeMeter:   4,
        Fader:         4,
        Transition:    5,  # released before plain Sources (it's a Source subclass)
        Filter:        5,
        SceneItem:     6,
        Source:        7,
        Scene:         8,
    }

    with _wrappers_lock:
        snapshot = list(_wrappers)
        _wrappers.clear()

    def order_key(w):
        for cls, rank in _ORDER.items():
            if isinstance(w, cls):
                return rank
        return 99

    snapshot.sort(key=order_key)

    # Before releasing anything, empty every live scene of its items.
    #
    # obs_scene_release() alone does not destroy a scene synchronously — the
    # actual teardown is deferred to libobs's video/graphics thread. If a scene
    # still holds items when obs_shutdown() runs, that deferred destroy fires on
    # the video thread (obs_sceneitem_release -> obs_source_release) at the same
    # time obs_shutdown() frees the remaining sources on the main thread — a
    # double-free that segfaults on Linux. obs_sceneitem_remove() drops the
    # scene's reference to each item's source *synchronously* on this thread, so
    # by the time obs_shutdown() runs there is nothing left to race on.
    #
    # We enumerate scenes via obs_enum_scenes() rather than walking our tracked
    # wrappers: a user (or the studio) may have dropped a Scene wrapper whose
    # underlying scene is still alive in libobs, and that scene's items would
    # otherwise never be cleared. See tests/integration/test_shutdown.py.
    lib = get_lib()

    @ffi.callback("bool(obs_scene_t *, obs_sceneitem_t *, void *)")
    def _remove_item(_scene_ptr, item_ptr, _param):
        try:
            lib.obs_sceneitem_remove(item_ptr)
        except Exception:
            pass
        return True

    @ffi.callback("bool(void *, obs_source_t *)")
    def _empty_scene(_param, source_ptr):
        try:
            scene_ptr = lib.obs_scene_from_source(source_ptr)
            if scene_ptr != ffi.NULL:
                lib.obs_scene_enum_items(scene_ptr, _remove_item, ffi.NULL)
        except Exception:
            pass
        return True

    try:
        lib.obs_enum_scenes(_empty_scene, ffi.NULL)
    except Exception:
        pass

    for w in snapshot:
        try:
            w.release()
        except Exception:
            pass


def lib():
    """Shorthand alias used across the package."""
    return get_lib()
