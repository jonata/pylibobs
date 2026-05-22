"""
Scene / SceneItem — wrappers for obs_scene_t and obs_sceneitem_t.

OBS 32+: scenes no longer have addref. Lifetime is owned by whoever calls
obs_scene_create (which returns a strong ref). Scene items still have addref.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, IntFlag
from typing import Iterator

from ._ffi import ffi, get_lib, is_alive, register_wrapper
from .source import Source


# Alignment flags — combine via bitwise OR
class Alignment(IntFlag):
    CENTER = 0
    LEFT   = 1 << 0
    RIGHT  = 1 << 1
    TOP    = 1 << 2
    BOTTOM = 1 << 3


class BoundsType(IntEnum):
    NONE             = 0
    STRETCH          = 1
    SCALE_INNER      = 2
    SCALE_OUTER      = 3
    SCALE_TO_WIDTH   = 4
    SCALE_TO_HEIGHT  = 5
    MAX_ONLY         = 6


class BlendingMode(IntEnum):
    NORMAL    = 0
    ADDITIVE  = 1
    SUBTRACT  = 2
    SCREEN    = 3
    MULTIPLY  = 4
    LIGHTEN   = 5
    DARKEN    = 6


class BlendingMethod(IntEnum):
    DEFAULT  = 0
    SRGB_OFF = 1


@dataclass
class TransformInfo:
    """Snapshot of a scene item's full transform — mirrors obs_transform_info."""
    pos:               tuple[float, float]            = (0.0, 0.0)
    rotation:          float                          = 0.0
    scale:             tuple[float, float]            = (1.0, 1.0)
    alignment:         int                            = int(Alignment.LEFT | Alignment.TOP)
    bounds_type:       int                            = int(BoundsType.NONE)
    bounds_alignment:  int                            = int(Alignment.CENTER)
    bounds:            tuple[float, float]            = (0.0, 0.0)
    crop_to_bounds:    bool                           = False
    bounds_crop:       tuple[int, int, int, int]      = (0, 0, 0, 0)


class SceneItem:
    """Wraps obs_sceneitem_t. Always owns its reference."""

    __slots__ = ("_ptr", "_owned", "__weakref__")

    def __init__(self, ptr, *, owned: bool = True) -> None:
        if ptr == ffi.NULL:
            raise ValueError("Cannot wrap NULL obs_sceneitem_t pointer")
        self._ptr = ptr
        self._owned = owned
        if owned:
            get_lib().obs_sceneitem_addref(self._ptr)
            register_wrapper(self)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def source(self) -> Source:
        # obs_sceneitem_get_source returns a borrowed reference
        ptr = get_lib().obs_sceneitem_get_source(self._ptr)
        return Source.borrow(ptr)

    @property
    def visible(self) -> bool:
        return bool(get_lib().obs_sceneitem_visible(self._ptr))

    @visible.setter
    def visible(self, value: bool) -> None:
        get_lib().obs_sceneitem_set_visible(self._ptr, value)

    @property
    def locked(self) -> bool:
        return bool(get_lib().obs_sceneitem_locked(self._ptr))

    @locked.setter
    def locked(self, value: bool) -> None:
        get_lib().obs_sceneitem_set_locked(self._ptr, value)

    @property
    def order_position(self) -> int:
        return int(get_lib().obs_sceneitem_get_order_position(self._ptr))

    @order_position.setter
    def order_position(self, value: int) -> None:
        get_lib().obs_sceneitem_set_order_position(self._ptr, value)

    @property
    def is_group(self) -> bool:
        return bool(get_lib().obs_sceneitem_is_group(self._ptr))

    # ------------------------------------------------------------------
    # Position / scale / rotation
    # ------------------------------------------------------------------

    @property
    def pos(self) -> tuple[float, float]:
        v = ffi.new("struct vec2 *")
        get_lib().obs_sceneitem_get_pos(self._ptr, v)
        return (v.x, v.y)

    @pos.setter
    def pos(self, xy: tuple[float, float]) -> None:
        v = ffi.new("struct vec2 *")
        v.x, v.y = float(xy[0]), float(xy[1])
        get_lib().obs_sceneitem_set_pos(self._ptr, v)

    @property
    def scale(self) -> tuple[float, float]:
        v = ffi.new("struct vec2 *")
        get_lib().obs_sceneitem_get_scale(self._ptr, v)
        return (v.x, v.y)

    @scale.setter
    def scale(self, sxy: tuple[float, float]) -> None:
        v = ffi.new("struct vec2 *")
        v.x, v.y = float(sxy[0]), float(sxy[1])
        get_lib().obs_sceneitem_set_scale(self._ptr, v)

    @property
    def rotation(self) -> float:
        return float(get_lib().obs_sceneitem_get_rot(self._ptr))

    @rotation.setter
    def rotation(self, deg: float) -> None:
        get_lib().obs_sceneitem_set_rot(self._ptr, float(deg))

    # ------------------------------------------------------------------
    # Alignment — anchor point. Bit flags:
    #   center=0, left=1, right=2, top=4, bottom=8
    # ------------------------------------------------------------------
    @property
    def alignment(self) -> int:
        return int(get_lib().obs_sceneitem_get_alignment(self._ptr))

    @alignment.setter
    def alignment(self, value: int) -> None:
        get_lib().obs_sceneitem_set_alignment(self._ptr, int(value))

    # ------------------------------------------------------------------
    # Bounds — constrain the item to fit/stretch into a box
    # ------------------------------------------------------------------
    @property
    def bounds_type(self) -> int:
        return int(get_lib().obs_sceneitem_get_bounds_type(self._ptr))

    @bounds_type.setter
    def bounds_type(self, value: int) -> None:
        get_lib().obs_sceneitem_set_bounds_type(self._ptr, int(value))

    @property
    def bounds_alignment(self) -> int:
        return int(get_lib().obs_sceneitem_get_bounds_alignment(self._ptr))

    @bounds_alignment.setter
    def bounds_alignment(self, value: int) -> None:
        get_lib().obs_sceneitem_set_bounds_alignment(self._ptr, int(value))

    @property
    def bounds(self) -> tuple[float, float]:
        v = ffi.new("struct vec2 *")
        get_lib().obs_sceneitem_get_bounds(self._ptr, v)
        return (v.x, v.y)

    @bounds.setter
    def bounds(self, wh: tuple[float, float]) -> None:
        v = ffi.new("struct vec2 *")
        v.x, v.y = float(wh[0]), float(wh[1])
        get_lib().obs_sceneitem_set_bounds(self._ptr, v)

    # ------------------------------------------------------------------
    # Crop — pixel-precise per-side crop applied before scaling
    # ------------------------------------------------------------------
    @property
    def crop(self) -> tuple[int, int, int, int]:
        c = ffi.new("struct obs_sceneitem_crop *")
        get_lib().obs_sceneitem_get_crop(self._ptr, c)
        return (c.left, c.top, c.right, c.bottom)

    @crop.setter
    def crop(self, ltrb: tuple[int, int, int, int]) -> None:
        c = ffi.new("struct obs_sceneitem_crop *")
        c.left, c.top, c.right, c.bottom = (int(x) for x in ltrb)
        get_lib().obs_sceneitem_set_crop(self._ptr, c)

    # ------------------------------------------------------------------
    # Blending — how this item composites onto layers beneath it
    # ------------------------------------------------------------------
    @property
    def blending_mode(self) -> int:
        return int(get_lib().obs_sceneitem_get_blending_mode(self._ptr))

    @blending_mode.setter
    def blending_mode(self, value: int) -> None:
        get_lib().obs_sceneitem_set_blending_mode(self._ptr, int(value))

    @property
    def blending_method(self) -> int:
        return int(get_lib().obs_sceneitem_get_blending_method(self._ptr))

    @blending_method.setter
    def blending_method(self, value: int) -> None:
        get_lib().obs_sceneitem_set_blending_method(self._ptr, int(value))

    # ------------------------------------------------------------------
    # Bulk transform info — read/write entire transform struct in one call
    # ------------------------------------------------------------------
    def get_transform(self) -> "TransformInfo":
        info = ffi.new("struct obs_transform_info *")
        get_lib().obs_sceneitem_get_info2(self._ptr, info)
        crop = (info.bounds_crop.left, info.bounds_crop.top,
                info.bounds_crop.right, info.bounds_crop.bottom)
        return TransformInfo(
            pos=(info.pos.x, info.pos.y),
            rotation=float(info.rot),
            scale=(info.scale.x, info.scale.y),
            alignment=int(info.alignment),
            bounds_type=int(info.bounds_type),
            bounds_alignment=int(info.bounds_alignment),
            bounds=(info.bounds.x, info.bounds.y),
            crop_to_bounds=bool(info.crop_to_bounds),
            bounds_crop=crop,
        )

    def set_transform(self, tr: "TransformInfo") -> None:
        info = ffi.new("struct obs_transform_info *")
        info.pos.x, info.pos.y = tr.pos
        info.rot = float(tr.rotation)
        info.scale.x, info.scale.y = tr.scale
        info.alignment = int(tr.alignment)
        info.bounds_type = int(tr.bounds_type)
        info.bounds_alignment = int(tr.bounds_alignment)
        info.bounds.x, info.bounds.y = tr.bounds
        info.crop_to_bounds = bool(tr.crop_to_bounds)
        info.bounds_crop.left, info.bounds_crop.top = tr.bounds_crop[0], tr.bounds_crop[1]
        info.bounds_crop.right, info.bounds_crop.bottom = tr.bounds_crop[2], tr.bounds_crop[3]
        get_lib().obs_sceneitem_set_info2(self._ptr, info)

    # ------------------------------------------------------------------
    # Defer / coalesce many edits so libobs computes the transform once
    # ------------------------------------------------------------------
    def defer_update_begin(self) -> None:
        get_lib().obs_sceneitem_defer_update_begin(self._ptr)

    def defer_update_end(self) -> None:
        get_lib().obs_sceneitem_defer_update_end(self._ptr)

    def force_update_transform(self) -> None:
        get_lib().obs_sceneitem_force_update_transform(self._ptr)

    def get_private_settings(self):
        from .data import OBSData
        ptr = get_lib().obs_sceneitem_get_private_settings(self._ptr)
        return OBSData(_ptr=ptr, _owned=True) if ptr != ffi.NULL else None

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def remove(self) -> None:
        get_lib().obs_sceneitem_remove(self._ptr)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def release(self) -> None:
        if self._ptr != ffi.NULL and self._owned and is_alive():
            get_lib().obs_sceneitem_release(self._ptr)
        self._ptr = ffi.NULL

    def __del__(self) -> None:
        try:
            self.release()
        except Exception:
            pass

    def __repr__(self) -> str:
        try:
            return f"SceneItem(source={self.source.name!r})"
        except Exception:
            return f"SceneItem(ptr={self._ptr})"


class Scene:
    """Wraps obs_scene_t."""

    __slots__ = ("_ptr", "_owned", "__weakref__")

    def __init__(self, ptr, *, owned: bool = True) -> None:
        if ptr == ffi.NULL:
            raise ValueError("Cannot wrap NULL obs_scene_t pointer")
        self._ptr = ptr
        self._owned = owned
        if owned:
            register_wrapper(self)

    # ------------------------------------------------------------------
    # Factory methods
    # ------------------------------------------------------------------

    @classmethod
    def create(cls, name: str) -> "Scene":
        ptr = get_lib().obs_scene_create(name.encode())
        if ptr == ffi.NULL:
            raise RuntimeError(f"obs_scene_create returned NULL for name={name!r}")
        return cls(ptr, owned=True)

    @classmethod
    def create_private(cls, name: str) -> "Scene":
        ptr = get_lib().obs_scene_create_private(name.encode())
        if ptr == ffi.NULL:
            raise RuntimeError(f"obs_scene_create_private returned NULL for name={name!r}")
        return cls(ptr, owned=True)

    @classmethod
    def from_source(cls, source: Source) -> "Scene | None":
        # obs_scene_from_source returns a borrowed ref
        ptr = get_lib().obs_scene_from_source(source._ptr)
        if ptr == ffi.NULL:
            return None
        return cls(ptr, owned=False)

    # ------------------------------------------------------------------
    # Items
    # ------------------------------------------------------------------

    def add(self, source: Source) -> SceneItem:
        # obs_scene_add returns a borrowed scene item; the scene retains it.
        ptr = get_lib().obs_scene_add(self._ptr, source._ptr)
        if ptr == ffi.NULL:
            raise RuntimeError("obs_scene_add returned NULL")
        return SceneItem(ptr, owned=True)  # bump refcount for Python ownership

    def add_group(self, name: str) -> SceneItem:
        """Create a new empty group scene item with the given name."""
        ptr = get_lib().obs_scene_add_group(self._ptr, name.encode())
        if ptr == ffi.NULL:
            raise RuntimeError(f"obs_scene_add_group returned NULL for {name!r}")
        return SceneItem(ptr, owned=True)

    def duplicate(self, name: str, dup_type: int = 1) -> "Scene":
        """Duplicate this scene. dup_type: 0=share refs, 1=copy private, 2=full copy."""
        ptr = get_lib().obs_scene_duplicate(self._ptr, name.encode(), int(dup_type))
        if ptr == ffi.NULL:
            raise RuntimeError(f"obs_scene_duplicate returned NULL for {name!r}")
        sc = Scene.__new__(Scene)
        sc._ptr = ptr
        sc._owned = True
        register_wrapper(sc)
        return sc

    def find(self, name: str) -> "SceneItem | None":
        ptr = get_lib().obs_scene_find_source(self._ptr, name.encode())
        return SceneItem(ptr, owned=True) if ptr != ffi.NULL else None

    def items(self) -> list[SceneItem]:
        """Return all scene items (snapshot of current order)."""
        collected: list[SceneItem] = []

        @ffi.callback("bool(obs_scene_t *, obs_sceneitem_t *, void *)")
        def _cb(scene_ptr, item_ptr, _param):
            collected.append(SceneItem(item_ptr, owned=True))
            return True

        get_lib().obs_scene_enum_items(self._ptr, _cb, ffi.NULL)
        return collected

    def __iter__(self) -> Iterator[SceneItem]:
        return iter(self.items())

    def __len__(self) -> int:
        return len(self.items())

    # ------------------------------------------------------------------
    # Source view
    # ------------------------------------------------------------------

    def as_source(self) -> Source:
        """Return a BORROWED Source view of the scene (do not release)."""
        ptr = get_lib().obs_scene_get_source(self._ptr)
        return Source.borrow(ptr)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def release(self) -> None:
        if self._ptr != ffi.NULL and self._owned and is_alive():
            get_lib().obs_scene_release(self._ptr)
        self._ptr = ffi.NULL

    def __del__(self) -> None:
        try:
            self.release()
        except Exception:
            pass

    def __repr__(self) -> str:
        return f"Scene(ptr={self._ptr}, owned={self._owned})"
