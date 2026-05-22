"""
Properties — Pythonic wrapper for obs_properties_t / obs_property_t.

Lets you enumerate the configurable settings of a source (or other config'd
object), find list-type properties, and read out their available choices.

Typical use::

    src = Source.create("monitor_capture", "Display")
    props = Properties.from_source(src)
    for p in props:
        if p.type == PropertyType.LIST:
            print(p.name, p.format, p.items)

    # Pick the second monitor:
    src.update({"monitor_id": props["monitor_id"].items[1].value})
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Iterator

from ._ffi import ffi, get_lib


class PropertyType(IntEnum):
    INVALID        = 0
    BOOL           = 1
    INT            = 2
    FLOAT          = 3
    TEXT           = 4
    PATH           = 5
    LIST           = 6
    COLOR          = 7
    BUTTON         = 8
    FONT           = 9
    EDITABLE_LIST  = 10
    FRAME_RATE     = 11
    GROUP          = 12
    COLOR_ALPHA    = 13


class ComboFormat(IntEnum):
    INVALID = 0
    INT     = 1
    FLOAT   = 2
    STRING  = 3
    BOOL    = 4


@dataclass(frozen=True)
class ListItem:
    """One choice in a LIST-type property."""
    name: str
    value: str | int | float | bool
    disabled: bool = False


@dataclass
class IntRange:
    min: int
    max: int
    step: int
    type: int      # 0 = scroller (spinbox), 1 = slider
    suffix: str = ""


@dataclass
class FloatRange:
    min: float
    max: float
    step: float
    type: int
    suffix: str = ""


@dataclass
class TextInfo:
    type: int          # 0 default, 1 password, 2 multiline, 3 info
    info_type: int     # for info text — 0 normal, 1 warning, 2 error
    word_wrap: bool
    monospace: bool


@dataclass
class PathInfo:
    type: int          # 0 file, 1 directory, 2 file_save
    filter: str        # glob filter, e.g. "Images (*.png *.jpg)"
    default_path: str


@dataclass
class Property:
    """A single property of a source."""
    name: str
    description: str
    type: PropertyType
    visible: bool
    enabled: bool
    format: ComboFormat | None = None    # only meaningful for LIST
    items: list[ListItem] = None         # only populated for LIST
    int_range:   IntRange   | None = None
    float_range: FloatRange | None = None
    text_info:   TextInfo   | None = None
    path_info:   PathInfo   | None = None
    long_description: str = ""

    def __post_init__(self):
        if self.items is None:
            self.items = []


class Properties:
    """Wraps obs_properties_t. Holds the underlying pointer plus a parsed list."""

    __slots__ = ("_ptr", "_props")

    def __init__(self, ptr) -> None:
        if ptr == ffi.NULL:
            raise ValueError("Cannot wrap NULL obs_properties_t pointer")
        self._ptr = ptr
        self._props: list[Property] = []
        self._enumerate()

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------

    @classmethod
    def from_source(cls, source) -> "Properties":
        lib = get_lib()
        ptr = lib.obs_source_properties(source._ptr)
        if ptr == ffi.NULL:
            raise RuntimeError("obs_source_properties returned NULL")
        return cls(ptr)

    @classmethod
    def from_source_id(cls, source_id: str) -> "Properties":
        """Get default properties for a source type without instantiating it."""
        lib = get_lib()
        ptr = lib.obs_get_source_properties(source_id.encode())
        if ptr == ffi.NULL:
            raise RuntimeError(f"obs_get_source_properties returned NULL for {source_id!r}")
        return cls(ptr)

    @classmethod
    def from_encoder_id(cls, encoder_id: str) -> "Properties":
        ptr = get_lib().obs_get_encoder_properties(encoder_id.encode())
        if ptr == ffi.NULL:
            raise RuntimeError(f"obs_get_encoder_properties returned NULL for {encoder_id!r}")
        return cls(ptr)

    @classmethod
    def from_output_id(cls, output_id: str) -> "Properties":
        ptr = get_lib().obs_get_output_properties(output_id.encode())
        if ptr == ffi.NULL:
            raise RuntimeError(f"obs_get_output_properties returned NULL for {output_id!r}")
        return cls(ptr)

    @classmethod
    def from_service_id(cls, service_id: str) -> "Properties":
        ptr = get_lib().obs_get_service_properties(service_id.encode())
        if ptr == ffi.NULL:
            raise RuntimeError(f"obs_get_service_properties returned NULL for {service_id!r}")
        return cls(ptr)

    # ------------------------------------------------------------------
    # Enumeration
    # ------------------------------------------------------------------

    def _enumerate(self) -> None:
        lib = get_lib()
        holder = ffi.new("obs_property_t **")
        holder[0] = lib.obs_properties_first(self._ptr)
        while holder[0] != ffi.NULL:
            self._props.append(self._read_property(holder[0]))
            if not lib.obs_property_next(holder):
                break

    def _read_property(self, p) -> Property:
        lib = get_lib()
        name = _decode(lib.obs_property_name(p))
        desc = _decode(lib.obs_property_description(p))
        ptype = PropertyType(lib.obs_property_get_type(p))
        visible = bool(lib.obs_property_visible(p))
        enabled = bool(lib.obs_property_enabled(p))

        prop = Property(name=name, description=desc, type=ptype,
                        visible=visible, enabled=enabled)

        if ptype == PropertyType.LIST:
            prop.format = ComboFormat(lib.obs_property_list_format(p))
            count = int(lib.obs_property_list_item_count(p))
            for i in range(count):
                iname = _decode(lib.obs_property_list_item_name(p, i))
                idisabled = bool(lib.obs_property_list_item_disabled(p, i))
                if prop.format == ComboFormat.STRING:
                    raw = lib.obs_property_list_item_string(p, i)
                    ival = _decode(raw)
                elif prop.format == ComboFormat.INT:
                    ival = int(lib.obs_property_list_item_int(p, i))
                elif prop.format == ComboFormat.FLOAT:
                    ival = float(lib.obs_property_list_item_float(p, i))
                else:
                    ival = ""
                prop.items.append(ListItem(name=iname, value=ival, disabled=idisabled))

        elif ptype == PropertyType.INT:
            prop.int_range = IntRange(
                min=int(lib.obs_property_int_min(p)),
                max=int(lib.obs_property_int_max(p)),
                step=int(lib.obs_property_int_step(p)),
                type=int(lib.obs_property_int_type(p)),
                suffix=_decode(lib.obs_property_int_suffix(p)),
            )
        elif ptype == PropertyType.FLOAT:
            prop.float_range = FloatRange(
                min=float(lib.obs_property_float_min(p)),
                max=float(lib.obs_property_float_max(p)),
                step=float(lib.obs_property_float_step(p)),
                type=int(lib.obs_property_float_type(p)),
                suffix=_decode(lib.obs_property_float_suffix(p)),
            )
        elif ptype == PropertyType.TEXT:
            prop.text_info = TextInfo(
                type=int(lib.obs_property_text_type(p)),
                info_type=int(lib.obs_property_text_info_type(p)),
                word_wrap=bool(lib.obs_property_text_info_word_wrap(p)),
                monospace=bool(lib.obs_property_text_monospace(p)),
            )
        elif ptype == PropertyType.PATH:
            prop.path_info = PathInfo(
                type=int(lib.obs_property_path_type(p)),
                filter=_decode(lib.obs_property_path_filter(p)),
                default_path=_decode(lib.obs_property_path_default_path(p)),
            )

        # Long description (tooltip) — present on every property type
        prop.long_description = _decode(lib.obs_property_long_description(p))

        return prop

    # ------------------------------------------------------------------
    # Pythonic access
    # ------------------------------------------------------------------

    def __iter__(self) -> Iterator[Property]:
        return iter(self._props)

    def __len__(self) -> int:
        return len(self._props)

    def __contains__(self, name: str) -> bool:
        return any(p.name == name for p in self._props)

    def __getitem__(self, name: str) -> Property:
        for p in self._props:
            if p.name == name:
                return p
        raise KeyError(name)

    def get(self, name: str, default=None):
        try:
            return self[name]
        except KeyError:
            return default

    def names(self) -> list[str]:
        return [p.name for p in self._props]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def release(self) -> None:
        if self._ptr != ffi.NULL:
            try:
                get_lib().obs_properties_destroy(self._ptr)
            except Exception:
                pass
            self._ptr = ffi.NULL

    def __del__(self) -> None:
        try:
            self.release()
        except Exception:
            pass


def _decode(cdata) -> str:
    if cdata == ffi.NULL:
        return ""
    return ffi.string(cdata).decode("utf-8", errors="replace")
