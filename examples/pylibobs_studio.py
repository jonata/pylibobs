"""
pylibobs_studio.py — an OBS-like application built entirely on tkinter.

Stdlib only (tkinter is in the standard library). Run:
    python examples/pylibobs_studio.py

Features:
  • Live preview of the program output (libobs renders directly into a
    tkinter Frame via its native window handle — no Qt, no GTK)
  • Multiple scenes, switchable via a list
  • Per-scene sources: add (with type picker), remove, reorder, toggle
    visibility
  • Add-source flow handles monitor/window pickers and file-source pickers
    automatically based on the chosen type
  • Audio mixer with live VU meters (green/yellow/red), volume sliders
    (IEC curve), and mute toggles per audio source
  • Recording controls with live frames/bytes/dropped-frames stats

All sourced by enumerating libobs at runtime — what shows up in the
"Add source" menu is what your bundled OBS has registered.
"""

from __future__ import annotations

import queue
import sys
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, simpledialog, ttk
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).parent.parent))

from pylibobs import (
    AudioEncoder, ComboFormat, Display, Fader, FaderType, OBSContext,
    OBSData, Output, Properties, PropertyType, Scene, Service, Source,
    VideoEncoder, VolumeMeter, enum_input_types, get_source_display_name,
    render_main_texture_letterboxed,
)
from pylibobs._ffi import get_lib


# Common RTMP ingest URLs — picked when the streaming preset combo changes
STREAMING_PRESETS = {
    "Custom":   "",
    "YouTube":  "rtmp://a.rtmp.youtube.com/live2",
    "Twitch":   "rtmp://live.twitch.tv/app",
    "Facebook": "rtmps://live-api-s.facebook.com:443/rtmp/",
    "Restream": "rtmp://live.restream.io/live",
}


CANVAS_W, CANVAS_H, FPS = 1280, 720, 30
RECORDING_DEFAULTS = {"rate_control": "CRF", "crf": 23, "preset": "veryfast"}


# ==========================================================================
# Mixer row — one widget per audio-capable source in the current scene
# ==========================================================================
class MixerRow(ttk.Frame):
    """One mixer strip: source name, VU bar, volume slider, mute checkbox."""

    def __init__(self, parent, source: Source) -> None:
        super().__init__(parent, padding=(4, 2))
        self.source = source
        self._peak_q: queue.Queue[float] = queue.Queue(maxsize=8)

        # Header — source name + level readout
        header = ttk.Frame(self)
        header.pack(fill="x")
        ttk.Label(header, text=source.name, font=("Segoe UI", 9, "bold")).pack(side="left")
        self._db_var = tk.StringVar(value="-inf dB")
        ttk.Label(header, textvariable=self._db_var,
                  font=("Consolas", 8)).pack(side="right")

        # VU meter
        self.meter = tk.Canvas(self, height=10, bg="#1a1a1a",
                               highlightthickness=0)
        self.meter.pack(fill="x", pady=(2, 2))

        # Volume slider (IEC dB curve via Fader.deflection)
        self.fader = Fader.create(FaderType.IEC)
        try:
            self.fader.attach(source)
        except RuntimeError:
            pass    # source might not actually carry audio
        ctl = ttk.Frame(self)
        ctl.pack(fill="x")
        self._vol_var = tk.DoubleVar(value=self.fader.deflection)
        slider = ttk.Scale(ctl, from_=0.0, to=1.0, orient="horizontal",
                           variable=self._vol_var,
                           command=lambda _: self._set_vol())
        slider.pack(side="left", fill="x", expand=True)
        self._mute_var = tk.BooleanVar(value=source.muted)
        ttk.Checkbutton(ctl, text="M", variable=self._mute_var,
                        command=self._toggle_mute, width=3).pack(side="left", padx=(4, 0))

        # Volume meter callback (fires on libobs's audio thread; we queue
        # and let the main loop's tick read the queue.)
        self.volmeter = VolumeMeter.create()
        try:
            self.volmeter.attach(source)
        except RuntimeError:
            pass
        self.volmeter.add_callback(self._on_levels)

    # ----- callbacks (libobs threads) ----------------------------------
    def _on_levels(self, mag, peak, input_peak) -> None:
        try:
            self._peak_q.put_nowait(max(peak[:2]))   # max of L+R
        except queue.Full:
            pass

    def _set_vol(self) -> None:
        try:
            self.fader.deflection = float(self._vol_var.get())
        except Exception:
            pass

    def _toggle_mute(self) -> None:
        try:
            self.source.muted = self._mute_var.get()
        except Exception:
            pass

    # ----- ticked from main thread -------------------------------------
    def update_ui(self) -> None:
        """Drain the levels queue and repaint the VU bar."""
        latest: float | None = None
        try:
            while True:
                latest = self._peak_q.get_nowait()
        except queue.Empty:
            pass
        if latest is None:
            return

        # Repaint
        self.meter.delete("all")
        w = max(self.meter.winfo_width(), 1)
        db = max(-60.0, min(0.0, latest))
        ratio = (db + 60.0) / 60.0
        if db >= -3.0:
            color = "#ff3333"
        elif db >= -12.0:
            color = "#ffcc00"
        else:
            color = "#33cc33"
        self.meter.create_rectangle(0, 0, int(w * ratio), 10,
                                    fill=color, outline="")
        if db <= -59.5:
            self._db_var.set("-inf dB")
        else:
            self._db_var.set(f"{db:+.1f} dB")

    def cleanup(self) -> None:
        try: self.volmeter.release()
        except Exception: pass
        try: self.fader.release()
        except Exception: pass


# ==========================================================================
# Add-source dialog — picks a type + name; the rest is type-specific
# ==========================================================================
class AddSourceDialog(tk.Toplevel):
    """Modal dialog: pick a source type (filtered to inputs) and a name."""

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.title("Add source")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.result: tuple[str, str] | None = None

        # Build the picker
        types = enum_input_types()
        # Friendly (display name, id) pairs, sorted by display name
        pairs = sorted(
            ((get_source_display_name(sid) or sid, sid) for sid in types),
            key=lambda x: x[0].lower(),
        )
        self._id_by_label = {f"{disp}  [{sid}]": sid for disp, sid in pairs}

        ttk.Label(self, text="Source type:").grid(row=0, column=0, sticky="w",
                                                  padx=8, pady=(8, 2))
        self._type_var = tk.StringVar()
        type_cb = ttk.Combobox(self, textvariable=self._type_var,
                               values=list(self._id_by_label.keys()),
                               state="readonly", width=48)
        type_cb.grid(row=1, column=0, columnspan=2, padx=8, pady=2, sticky="ew")
        if self._id_by_label:
            type_cb.current(0)

        ttk.Label(self, text="Name:").grid(row=2, column=0, sticky="w",
                                            padx=8, pady=(8, 2))
        self._name_var = tk.StringVar(value="New source")
        ttk.Entry(self, textvariable=self._name_var, width=48).grid(
            row=3, column=0, columnspan=2, padx=8, pady=2, sticky="ew",
        )

        btns = ttk.Frame(self)
        btns.grid(row=4, column=0, columnspan=2, sticky="e", padx=8, pady=8)
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(btns, text="OK", command=self._ok).pack(side="right", padx=4)

        self.bind("<Return>", lambda _: self._ok())
        self.bind("<Escape>", lambda _: self.destroy())

    def _ok(self) -> None:
        sid = self._id_by_label.get(self._type_var.get())
        name = self._name_var.get().strip()
        if not sid or not name:
            return
        self.result = (sid, name)
        self.destroy()


# ==========================================================================
# Property picker — for monitor_id / window / etc.
# ==========================================================================
def pick_list_property(parent, source: Source, prop_name: str,
                       title: str) -> str | None:
    """Show a dropdown of valid string values for a LIST-typed property.
    Returns the chosen value, or None on cancel."""
    try:
        props = Properties.from_source(source)
    except Exception:
        return None
    prop = props.get(prop_name)
    if not prop or prop.type != PropertyType.LIST:
        return None

    rows = [(it.name, it.value) for it in prop.items
            if isinstance(it.value, str)
            and it.value and it.value != "DUMMY"
            and not it.disabled]
    if not rows:
        messagebox.showinfo("No options",
                            f"libobs reports no available '{prop_name}'.")
        return None

    dlg = tk.Toplevel(parent)
    dlg.title(title)
    dlg.transient(parent)
    dlg.grab_set()
    dlg.resizable(False, False)

    ttk.Label(dlg, text=prop.description or prop_name).pack(
        anchor="w", padx=8, pady=(8, 2),
    )
    var = tk.StringVar(value=rows[0][0])
    cb = ttk.Combobox(dlg, textvariable=var, state="readonly", width=48,
                      values=[r[0] for r in rows])
    cb.pack(padx=8, pady=2, fill="x")
    cb.current(0)

    result: dict[str, str | None] = {"v": None}

    def ok():
        for label, value in rows:
            if label == var.get():
                result["v"] = value
                break
        dlg.destroy()

    btns = ttk.Frame(dlg)
    btns.pack(fill="x", padx=8, pady=8)
    ttk.Button(btns, text="Cancel", command=dlg.destroy).pack(side="right")
    ttk.Button(btns, text="OK", command=ok).pack(side="right", padx=4)

    dlg.wait_window()
    return result["v"]


# ==========================================================================
# Properties editor — full live-editing dialog driven by libobs metadata
# ==========================================================================
class PropertiesDialog(tk.Toplevel):
    """A scrollable property editor populated dynamically from the source's
    `obs_source_properties()`. Handles BOOL / INT / FLOAT / TEXT / PATH /
    LIST / COLOR. Click "Apply" to push pending edits to the source.

    If a `SceneItem` is also passed, a *Transform* section is added at the
    top with live-updating Position / Scale / Rotation / Crop / Visible
    controls. Transform changes apply immediately (no Apply roundtrip)
    because they edit the scene item, not the underlying source.
    """

    def __init__(self, parent, source: Source, item=None) -> None:
        super().__init__(parent)
        self.source = source
        self.item   = item        # may be None if the source isn't on a scene
        self.title(f"Properties — {source.name}")
        self.transient(parent)
        self.grab_set()
        self.geometry("520x680")
        self.minsize(420, 360)

        self._edits: dict[str, Any] = {}

        # Scrollable form container
        outer = ttk.Frame(self)
        outer.pack(fill="both", expand=True, padx=4, pady=4)
        canvas = tk.Canvas(outer, highlightthickness=0)
        vsb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        self._form = ttk.Frame(canvas, padding=8)
        form_id = canvas.create_window((0, 0), window=self._form, anchor="nw")

        def _on_form_config(_e):
            canvas.configure(scrollregion=canvas.bbox("all"))
        self._form.bind("<Configure>", _on_form_config)

        def _on_canvas_config(e):
            canvas.itemconfigure(form_id, width=e.width)
        canvas.bind("<Configure>", _on_canvas_config)

        # Mouse wheel scroll
        def _on_wheel(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_wheel)

        # Build rows
        try:
            props = Properties.from_source(source)
        except Exception as e:
            ttk.Label(self._form, text=f"Could not read properties: {e}").grid(row=0, column=0)
            props = []
        self._settings = source.get_settings()
        self._form.columnconfigure(1, weight=1)

        row = 0
        # Transform section (live updates — SceneItem properties don't
        # need an Apply roundtrip)
        if self.item is not None:
            row = self._add_transform_section(row)
        # Source-defined properties
        for prop in props:
            if not prop.visible:
                continue
            row = self._add_row(prop, row)

        # Footer
        btns = ttk.Frame(self, padding=8)
        btns.pack(fill="x")
        self._info_var = tk.StringVar(value=f"{row} property row{'s' if row != 1 else ''}")
        ttk.Label(btns, textvariable=self._info_var,
                  font=("Segoe UI", 8)).pack(side="left")
        ttk.Button(btns, text="Close", command=self.destroy).pack(side="right")
        ttk.Button(btns, text="Apply",
                   command=self._apply).pack(side="right", padx=4)
        self.bind("<Escape>", lambda _: self.destroy())

    # ----- form construction ------------------------------------------
    def _add_row(self, prop, row: int) -> int:
        label = prop.description or prop.name
        if prop.type == PropertyType.GROUP:
            ttk.Separator(self._form, orient="horizontal").grid(
                row=row, column=0, columnspan=2, sticky="ew", pady=(8, 2),
            )
            row += 1
            ttk.Label(self._form, text=label,
                      font=("Segoe UI", 9, "bold")).grid(
                row=row, column=0, columnspan=2, sticky="w", padx=2,
            )
            return row + 1

        ttk.Label(self._form, text=label).grid(
            row=row, column=0, sticky="nw", padx=4, pady=4,
        )
        widget = self._make_widget(prop)
        if widget is None:
            widget = ttk.Label(self._form, text=f"({prop.type.name} not editable)",
                               font=("Segoe UI", 8, "italic"))
        widget.grid(row=row, column=1, sticky="ew", padx=4, pady=2)
        if prop.long_description:
            row += 1
            ttk.Label(self._form, text=prop.long_description,
                      font=("Segoe UI", 8, "italic"),
                      foreground="#888", wraplength=300).grid(
                row=row, column=1, sticky="w", padx=4, pady=(0, 4),
            )
        if not prop.enabled and widget is not None:
            try: widget.state(["disabled"])
            except (tk.TclError, AttributeError): pass
        return row + 1

    # ------------------------------------------------------------------
    # Transform section (X / Y / scale / rotation / crop / visible)
    # ------------------------------------------------------------------
    def _add_transform_section(self, row: int) -> int:
        """Add Transform controls that live-update the SceneItem."""
        item = self.item

        ttk.Label(self._form, text="Transform",
                  font=("Segoe UI", 10, "bold")).grid(
            row=row, column=0, columnspan=2, sticky="w", padx=2, pady=(0, 4),
        )
        row += 1

        # Read current values once
        try:
            px, py = item.pos
            sx, sy = item.scale
            rot    = item.rotation
            crop   = item.crop
            vis    = item.visible
        except Exception:
            px = py = 0.0
            sx = sy = 1.0
            rot = 0.0
            crop = (0, 0, 0, 0)
            vis  = True

        # ---- Variables ----
        self._tr_px  = tk.DoubleVar(value=px)
        self._tr_py  = tk.DoubleVar(value=py)
        self._tr_sx  = tk.DoubleVar(value=sx)
        self._tr_sy  = tk.DoubleVar(value=sy)
        self._tr_rot = tk.DoubleVar(value=rot)
        self._tr_cl  = tk.IntVar(value=crop[0])
        self._tr_ct  = tk.IntVar(value=crop[1])
        self._tr_cr  = tk.IntVar(value=crop[2])
        self._tr_cb  = tk.IntVar(value=crop[3])
        self._tr_vis = tk.BooleanVar(value=vis)

        # ---- Live-push callbacks ----
        def _push_pos(*_a):
            try: item.pos = (float(self._tr_px.get()), float(self._tr_py.get()))
            except (tk.TclError, ValueError, Exception): pass

        def _push_scale(*_a):
            try:
                sx = max(0.01, float(self._tr_sx.get()))
                sy = max(0.01, float(self._tr_sy.get()))
                item.scale = (sx, sy)
            except (tk.TclError, ValueError, Exception): pass

        def _push_rot(*_a):
            try: item.rotation = float(self._tr_rot.get())
            except (tk.TclError, ValueError, Exception): pass

        def _push_crop(*_a):
            try:
                item.crop = (max(0, int(self._tr_cl.get())),
                             max(0, int(self._tr_ct.get())),
                             max(0, int(self._tr_cr.get())),
                             max(0, int(self._tr_cb.get())))
            except (tk.TclError, ValueError, Exception): pass

        def _push_vis(*_a):
            try: item.visible = bool(self._tr_vis.get())
            except Exception: pass

        for v in (self._tr_px, self._tr_py):  v.trace_add("write", _push_pos)
        for v in (self._tr_sx, self._tr_sy):  v.trace_add("write", _push_scale)
        self._tr_rot.trace_add("write", _push_rot)
        for v in (self._tr_cl, self._tr_ct, self._tr_cr, self._tr_cb):
            v.trace_add("write", _push_crop)

        # ---- Helpers to build rows ----
        def _pair_row(label_text, var_a, var_b, sub_a, sub_b,
                      from_, to_, increment, fmt=None):
            nonlocal row
            ttk.Label(self._form, text=label_text).grid(
                row=row, column=0, sticky="w", padx=4, pady=2,
            )
            cell = ttk.Frame(self._form)
            cell.grid(row=row, column=1, sticky="ew", padx=4, pady=2)
            ttk.Label(cell, text=sub_a, font=("Segoe UI", 8)).pack(side="left")
            kw = {"format": fmt} if fmt else {}
            ttk.Spinbox(cell, from_=from_, to=to_, increment=increment,
                        textvariable=var_a, width=8, **kw).pack(
                side="left", padx=(2, 8),
            )
            ttk.Label(cell, text=sub_b, font=("Segoe UI", 8)).pack(side="left")
            ttk.Spinbox(cell, from_=from_, to=to_, increment=increment,
                        textvariable=var_b, width=8, **kw).pack(
                side="left", padx=2,
            )
            row += 1

        # ---- Build rows ----
        _pair_row("Position",   self._tr_px, self._tr_py, "X", "Y",
                  -9999, 9999, 1.0)
        _pair_row("Scale",      self._tr_sx, self._tr_sy, "X", "Y",
                  0.01, 100.0, 0.1, fmt="%.2f")

        ttk.Label(self._form, text="Rotation").grid(
            row=row, column=0, sticky="w", padx=4, pady=2,
        )
        cell = ttk.Frame(self._form)
        cell.grid(row=row, column=1, sticky="ew", padx=4, pady=2)
        ttk.Spinbox(cell, from_=-360.0, to=360.0, increment=1.0,
                    textvariable=self._tr_rot, width=8,
                    format="%.1f").pack(side="left", padx=2)
        ttk.Label(cell, text="°", font=("Segoe UI", 9)).pack(side="left")
        row += 1

        # Crop (LTRB)
        ttk.Label(self._form, text="Crop (px)").grid(
            row=row, column=0, sticky="w", padx=4, pady=2,
        )
        cell = ttk.Frame(self._form)
        cell.grid(row=row, column=1, sticky="ew", padx=4, pady=2)
        for lbl, var in (("L", self._tr_cl), ("T", self._tr_ct),
                          ("R", self._tr_cr), ("B", self._tr_cb)):
            ttk.Label(cell, text=lbl, font=("Segoe UI", 8)).pack(side="left")
            ttk.Spinbox(cell, from_=0, to=99999, increment=1,
                        textvariable=var, width=6).pack(
                side="left", padx=(2, 6),
            )
        row += 1

        # Visible
        ttk.Label(self._form, text="Visible").grid(
            row=row, column=0, sticky="w", padx=4, pady=2,
        )
        ttk.Checkbutton(self._form, variable=self._tr_vis,
                        command=_push_vis).grid(
            row=row, column=1, sticky="w", padx=4, pady=2,
        )
        row += 1

        # Reset transform
        cell = ttk.Frame(self._form)
        cell.grid(row=row, column=1, sticky="w", padx=4, pady=(4, 2))
        def _reset():
            self._tr_px.set(0.0); self._tr_py.set(0.0)
            self._tr_sx.set(1.0); self._tr_sy.set(1.0)
            self._tr_rot.set(0.0)
            self._tr_cl.set(0); self._tr_ct.set(0)
            self._tr_cr.set(0); self._tr_cb.set(0)
        ttk.Button(cell, text="Reset transform", command=_reset).pack(side="left")
        row += 1

        # Separator before the source-defined properties
        ttk.Separator(self._form, orient="horizontal").grid(
            row=row, column=0, columnspan=2, sticky="ew", pady=(8, 4),
        )
        row += 1
        ttk.Label(self._form, text="Source properties",
                  font=("Segoe UI", 10, "bold")).grid(
            row=row, column=0, columnspan=2, sticky="w", padx=2, pady=(0, 4),
        )
        return row + 1

    def _make_widget(self, prop):
        name = prop.name
        s    = self._settings

        # --- BOOL ---
        if prop.type == PropertyType.BOOL:
            var = tk.BooleanVar(value=s.get_bool(name))
            def _on():
                self._edits[name] = var.get()
            return ttk.Checkbutton(self._form, variable=var, command=_on)

        # --- INT ---
        if prop.type == PropertyType.INT:
            cur = s.get_int(name)
            var = tk.IntVar(value=cur)
            def _on(*_a):
                try: self._edits[name] = int(var.get())
                except (tk.TclError, ValueError): pass
            if prop.int_range and prop.int_range.max > prop.int_range.min:
                frame = ttk.Frame(self._form)
                ttk.Scale(frame, from_=prop.int_range.min, to=prop.int_range.max,
                          orient="horizontal", variable=var).pack(
                    side="left", fill="x", expand=True,
                )
                ttk.Spinbox(frame, from_=prop.int_range.min,
                            to=prop.int_range.max,
                            increment=prop.int_range.step or 1,
                            width=8, textvariable=var).pack(
                    side="left", padx=(4, 0),
                )
                var.trace_add("write", _on)
                return frame
            sp = ttk.Spinbox(self._form, from_=-2**31, to=2**31 - 1,
                             textvariable=var, width=12)
            var.trace_add("write", _on)
            return sp

        # --- FLOAT ---
        if prop.type == PropertyType.FLOAT:
            cur = s.get_double(name)
            var = tk.DoubleVar(value=cur)
            def _on(*_a):
                try: self._edits[name] = float(var.get())
                except (tk.TclError, ValueError): pass
            if prop.float_range and prop.float_range.max > prop.float_range.min:
                frame = ttk.Frame(self._form)
                ttk.Scale(frame,
                          from_=prop.float_range.min, to=prop.float_range.max,
                          orient="horizontal", variable=var).pack(
                    side="left", fill="x", expand=True,
                )
                ttk.Spinbox(frame, from_=prop.float_range.min,
                            to=prop.float_range.max,
                            increment=prop.float_range.step or 0.1,
                            format="%.3f", width=8, textvariable=var).pack(
                    side="left", padx=(4, 0),
                )
                var.trace_add("write", _on)
                return frame
            sp = ttk.Spinbox(self._form, from_=-1e9, to=1e9, increment=0.1,
                             textvariable=var, width=12)
            var.trace_add("write", _on)
            return sp

        # --- TEXT ---
        if prop.type == PropertyType.TEXT:
            cur = s.get_string(name)
            show = ""
            multiline = False
            info_only = False
            if prop.text_info:
                # 0 default, 1 password, 2 multiline, 3 info
                show = "*" if prop.text_info.type == 1 else ""
                multiline = (prop.text_info.type == 2)
                info_only = (prop.text_info.type == 3)
            if info_only:
                return ttk.Label(self._form, text=cur, foreground="#666",
                                 wraplength=320)
            if multiline:
                txt = tk.Text(self._form, height=4, width=30, wrap="word")
                txt.insert("1.0", cur)
                def _on_change(_e=None):
                    self._edits[name] = txt.get("1.0", "end-1c")
                txt.bind("<KeyRelease>", _on_change)
                txt.bind("<FocusOut>", _on_change)
                return txt
            var = tk.StringVar(value=cur)
            def _on(*_a):
                self._edits[name] = var.get()
            var.trace_add("write", _on)
            return ttk.Entry(self._form, textvariable=var, show=show)

        # --- PATH ---
        if prop.type == PropertyType.PATH:
            cur = s.get_string(name)
            var = tk.StringVar(value=cur)
            def _on(*_a):
                self._edits[name] = var.get()
            var.trace_add("write", _on)
            frame = ttk.Frame(self._form)
            ttk.Entry(frame, textvariable=var).pack(
                side="left", fill="x", expand=True,
            )
            def _browse():
                ptype = prop.path_info.type if prop.path_info else 0
                filt = prop.path_info.filter if prop.path_info else "*.*"
                pairs = [tuple(p.split(maxsplit=1)) for p in filt.split(";;")] if filt else []
                ft = [(p[0], p[1]) for p in pairs if len(p) == 2] or [("All", "*.*")]
                start = Path(cur).parent if cur and Path(cur).exists() else None
                if ptype == 1:    # directory
                    path = filedialog.askdirectory(initialdir=str(start) if start else "")
                elif ptype == 2:  # file_save
                    path = filedialog.asksaveasfilename(filetypes=ft,
                                                         initialdir=str(start) if start else "")
                else:             # file_open
                    path = filedialog.askopenfilename(filetypes=ft,
                                                       initialdir=str(start) if start else "")
                if path:
                    var.set(path)
            ttk.Button(frame, text="Browse…", command=_browse,
                       width=10).pack(side="left", padx=(4, 0))
            return frame

        # --- LIST ---
        if prop.type == PropertyType.LIST:
            items = [it for it in prop.items if not it.disabled]
            labels = [it.name for it in items]
            label_to_value = {it.name: it.value for it in items}
            var = tk.StringVar()
            if prop.format == ComboFormat.STRING:
                cur_v = s.get_string(name)
            elif prop.format == ComboFormat.INT:
                cur_v = s.get_int(name)
            elif prop.format == ComboFormat.FLOAT:
                cur_v = s.get_double(name)
            else:
                cur_v = None
            cur_label = next((it.name for it in items if it.value == cur_v), "")
            var.set(cur_label)
            cb = ttk.Combobox(self._form, textvariable=var,
                              values=labels, state="readonly")
            def _on(_e=None):
                self._edits[name] = label_to_value.get(var.get(), "")
            cb.bind("<<ComboboxSelected>>", _on)
            return cb

        # --- COLOR / COLOR_ALPHA ---
        if prop.type in (PropertyType.COLOR, PropertyType.COLOR_ALPHA):
            cur_int = s.get_int(name)
            # libobs colour layout: 0xAABBGGRR
            r = cur_int & 0xFF
            g = (cur_int >> 8) & 0xFF
            b = (cur_int >> 16) & 0xFF
            cur_hex = f"#{r:02x}{g:02x}{b:02x}"
            frame = ttk.Frame(self._form)
            swatch = tk.Label(frame, width=4, bg=cur_hex,
                              relief="ridge", borderwidth=1)
            swatch.pack(side="left", padx=(0, 4))
            label = ttk.Label(frame, text=cur_hex.upper(),
                              font=("Consolas", 9))
            label.pack(side="left")
            def _pick():
                rgb, hx = colorchooser.askcolor(color=swatch.cget("bg"),
                                                 title=prop.description)
                if hx:
                    r2, g2, b2 = (int(hx[i:i+2], 16) for i in (1, 3, 5))
                    swatch.configure(bg=hx)
                    label.configure(text=hx.upper())
                    self._edits[name] = (0xFF << 24) | (b2 << 16) | (g2 << 8) | r2
            ttk.Button(frame, text="Pick…",
                       command=_pick).pack(side="left", padx=(8, 0))
            return frame

        # Unsupported types — Font, Button, Editable List, Frame Rate
        return None

    # ----- apply ------------------------------------------------------
    def _apply(self) -> None:
        if not self._edits:
            self._info_var.set("(no changes to apply)")
            return
        try:
            self.source.update(self._edits)
        except Exception as e:
            messagebox.showerror("Apply failed", repr(e))
            return
        n = len(self._edits)
        self._edits = {}
        # Reload settings so the form reflects what libobs actually stored
        # (it may have clamped / canonicalised values).
        self._settings = self.source.get_settings()
        self._info_var.set(f"applied {n} change{'s' if n != 1 else ''}")


# ==========================================================================
# Main studio app
# ==========================================================================
class PylibobsStudio:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.obs: OBSContext | None = None
        self.venc: VideoEncoder | None = None
        self.aenc: AudioEncoder | None = None
        self.output: Output | None = None
        self.display: Display | None = None

        # streaming pipeline (created lazily on first Start Stream)
        self.stream_output:  Output | None        = None
        self.stream_venc:    VideoEncoder | None  = None
        self.stream_aenc:    AudioEncoder | None  = None
        self.stream_service: Service | None       = None

        # data model
        self.scenes: list[dict] = []   # [{"name", "scene", "items": [{...}]}]
        self.current_scene_idx: int = -1
        self.mixer_rows: list[MixerRow] = []

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(50, self._init_obs)
        self._tick_status()
        self._tick_mixer()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        self.root.title("pylibobs-studio")
        self.root.geometry("1200x780")
        self.root.minsize(900, 600)

        # Row 0: preview (expands)
        # Row 1: scenes | sources | mixer
        # Row 2: file + record controls
        # Row 3: status bar
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=3)
        self.root.rowconfigure(1, weight=2)

        # === Preview pane ===
        self.preview = tk.Frame(self.root, bg="#0a0a0a", highlightthickness=0)
        self.preview.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self.preview.bind("<Configure>", self._on_preview_resize)

        # === Middle: scenes | sources | mixer ===
        mid = ttk.Frame(self.root)
        mid.grid(row=1, column=0, sticky="nsew", padx=4)
        mid.rowconfigure(0, weight=1)
        for c, w in [(0, 1), (1, 1), (2, 3)]:
            mid.columnconfigure(c, weight=w)

        # Scenes column
        scenes_lf = ttk.LabelFrame(mid, text="Scenes", padding=4)
        scenes_lf.grid(row=0, column=0, sticky="nsew", padx=(0, 2))
        self.scenes_list = tk.Listbox(scenes_lf, exportselection=False,
                                       activestyle="dotbox")
        self.scenes_list.pack(fill="both", expand=True)
        self.scenes_list.bind("<<ListboxSelect>>", self._on_scene_select)
        scn_btns = ttk.Frame(scenes_lf)
        scn_btns.pack(fill="x", pady=(4, 0))
        ttk.Button(scn_btns, text="+ Scene", width=10,
                   command=self._add_scene_prompt).pack(side="left")
        ttk.Button(scn_btns, text="− Remove", width=10,
                   command=self._remove_scene).pack(side="left", padx=2)

        # Sources column
        srcs_lf = ttk.LabelFrame(mid, text="Sources", padding=4)
        srcs_lf.grid(row=0, column=1, sticky="nsew", padx=2)
        self.sources_list = tk.Listbox(srcs_lf, exportselection=False,
                                        activestyle="dotbox")
        self.sources_list.pack(fill="both", expand=True)
        self.sources_list.bind("<<ListboxSelect>>", self._on_source_select)
        self.sources_list.bind("<Double-1>",
                                lambda _e: self._toggle_visibility())
        src_btns = ttk.Frame(srcs_lf)
        src_btns.pack(fill="x", pady=(4, 0))
        ttk.Button(src_btns, text="+ Source", width=10,
                   command=self._add_source_dialog).pack(side="left")
        ttk.Button(src_btns, text="− Remove", width=10,
                   command=self._remove_source).pack(side="left", padx=2)
        ttk.Button(src_btns, text="↑", width=3,
                   command=lambda: self._reorder(-1)).pack(side="left", padx=2)
        ttk.Button(src_btns, text="↓", width=3,
                   command=lambda: self._reorder(+1)).pack(side="left")
        ttk.Button(src_btns, text="Hide/Show", width=10,
                   command=self._toggle_visibility).pack(side="left", padx=2)
        ttk.Button(src_btns, text="Properties…", width=12,
                   command=self._open_properties).pack(side="left", padx=2)

        # Mixer column (scrollable)
        mix_lf = ttk.LabelFrame(mid, text="Audio mixer", padding=4)
        mix_lf.grid(row=0, column=2, sticky="nsew", padx=(2, 0))
        self.mixer_host = ttk.Frame(mix_lf)
        self.mixer_host.pack(fill="both", expand=True)

        # === Recording controls ===
        ctrl = ttk.Frame(self.root, padding=4)
        ctrl.grid(row=2, column=0, sticky="ew", padx=4)
        ttk.Label(ctrl, text="Output file:").pack(side="left")
        self.path_var = tk.StringVar(value=str(Path.cwd() / "recording.mkv"))
        ttk.Entry(ctrl, textvariable=self.path_var).pack(
            side="left", fill="x", expand=True, padx=4,
        )
        ttk.Button(ctrl, text="Browse…", command=self._browse).pack(side="left")
        self.rec_btn = ttk.Button(ctrl, text="● Record",
                                   command=self._start_recording)
        self.rec_btn.pack(side="left", padx=(8, 0))
        self.stop_btn = ttk.Button(ctrl, text="■ Stop",
                                    command=self._stop_recording,
                                    state="disabled")
        self.stop_btn.pack(side="left", padx=2)

        # === Streaming row ===
        stream_row = ttk.Frame(self.root, padding=4)
        stream_row.grid(row=3, column=0, sticky="ew", padx=4)
        ttk.Label(stream_row, text="Stream to:").pack(side="left")
        self.preset_var = tk.StringVar(value="YouTube")
        preset_cb = ttk.Combobox(stream_row, textvariable=self.preset_var,
                                  values=list(STREAMING_PRESETS.keys()),
                                  state="readonly", width=12)
        preset_cb.pack(side="left", padx=4)
        preset_cb.bind("<<ComboboxSelected>>", self._on_preset_change)

        ttk.Label(stream_row, text="Server:").pack(side="left", padx=(8, 0))
        self.stream_url_var = tk.StringVar(value=STREAMING_PRESETS["YouTube"])
        ttk.Entry(stream_row, textvariable=self.stream_url_var, width=32).pack(
            side="left", padx=4,
        )
        ttk.Label(stream_row, text="Key:").pack(side="left", padx=(8, 0))
        self.stream_key_var = tk.StringVar()
        ttk.Entry(stream_row, textvariable=self.stream_key_var, show="*",
                  width=24).pack(side="left", fill="x", expand=True, padx=4)

        self.stream_btn = ttk.Button(stream_row, text="📡 Stream",
                                      command=self._start_streaming)
        self.stream_btn.pack(side="left", padx=(8, 0))
        self.stream_stop_btn = ttk.Button(stream_row, text="■ Stop",
                                           command=self._stop_streaming,
                                           state="disabled")
        self.stream_stop_btn.pack(side="left", padx=2)

        # === Status bar ===
        self.status_var = tk.StringVar(value="Initialising libobs…")
        ttk.Label(self.root, textvariable=self.status_var, relief="sunken",
                  padding=(6, 2), font=("Consolas", 9)).grid(
            row=4, column=0, sticky="ew",
        )

    # ------------------------------------------------------------------
    # libobs lifecycle
    # ------------------------------------------------------------------
    def _init_obs(self) -> None:
        try:
            self.obs = OBSContext(locale="en-US")
            self.obs.startup()
            self.obs.set_video(CANVAS_W, CANVAS_H, fps_num=FPS)
            self.obs.set_audio()
            self.obs.load_modules()

            self.venc = VideoEncoder.create("obs_x264", "studio_v",
                                            RECORDING_DEFAULTS)
            self.aenc = AudioEncoder.create("ffmpeg_aac", "studio_a",
                                            {"bitrate": 160})
            self._attach_preview()
            # Seed a first scene
            self._add_scene("Scene 1")

            self.status_var.set(
                f"Ready  •  libobs {self.obs.version}  •  "
                f"{CANVAS_W}x{CANVAS_H}@{FPS}"
            )
        except Exception as exc:
            messagebox.showerror("libobs init failed", repr(exc))
            self.root.destroy()

    def _attach_preview(self) -> None:
        """Hand the preview Frame's HWND to libobs's display API."""
        self.root.update_idletasks()
        hwnd = int(self.preview.winfo_id())
        w = max(self.preview.winfo_width(), 100)
        h = max(self.preview.winfo_height(), 100)
        self.display = Display.from_window(hwnd, w, h)
        cw, ch = CANVAS_W, CANVAS_H

        def _draw(cx, cy):
            render_main_texture_letterboxed(cw, ch, cx, cy)

        self.display.add_draw_callback(_draw)

    def _on_preview_resize(self, ev) -> None:
        if self.display is not None:
            try:
                self.display.resize(max(ev.width, 1), max(ev.height, 1))
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Scenes
    # ------------------------------------------------------------------
    def _add_scene_prompt(self) -> None:
        name = simpledialog.askstring("New scene", "Scene name:", parent=self.root)
        if name and name.strip():
            self._add_scene(name.strip())

    def _add_scene(self, name: str) -> None:
        if self.obs is None:
            return
        scene = Scene.create(name)
        self.scenes.append({"name": name, "scene": scene, "items": []})
        self.scenes_list.insert("end", name)
        self.scenes_list.selection_clear(0, "end")
        self.scenes_list.selection_set(len(self.scenes) - 1)
        self._on_scene_select()

    def _remove_scene(self) -> None:
        if self.current_scene_idx < 0:
            return
        entry = self.scenes.pop(self.current_scene_idx)
        for ie in entry["items"]:
            try: ie["item"].remove()
            except Exception: pass
        try: entry["scene"].release()
        except Exception: pass
        self.scenes_list.delete(self.current_scene_idx)
        if self.scenes:
            self.scenes_list.selection_set(
                min(self.current_scene_idx, len(self.scenes) - 1)
            )
        self._on_scene_select()

    def _on_scene_select(self, _event=None) -> None:
        sel = self.scenes_list.curselection()
        self.current_scene_idx = sel[0] if sel else -1
        # Wire current scene to channel 0 (program)
        from pylibobs._ffi import ffi as _ffi
        if self.current_scene_idx >= 0:
            scene = self.scenes[self.current_scene_idx]["scene"]
            get_lib().obs_set_output_source(0, scene.as_source()._ptr)
        else:
            get_lib().obs_set_output_source(0, _ffi.NULL)
        self._refresh_sources_list()
        self._rebuild_mixer()

    # ------------------------------------------------------------------
    # Sources
    # ------------------------------------------------------------------
    def _current_scene(self) -> dict | None:
        if 0 <= self.current_scene_idx < len(self.scenes):
            return self.scenes[self.current_scene_idx]
        return None

    def _add_source_dialog(self) -> None:
        if self._current_scene() is None:
            messagebox.showwarning("No scene",
                                   "Create or select a scene first.")
            return
        dlg = AddSourceDialog(self.root)
        self.root.wait_window(dlg)
        if not dlg.result:
            return
        sid, name = dlg.result
        self._create_source(sid, name)

    def _create_source(self, source_id: str, name: str) -> None:
        scene_entry = self._current_scene()
        if scene_entry is None:
            return
        try:
            src = Source.create(source_id, name)
        except RuntimeError as e:
            messagebox.showerror("Source creation failed", repr(e))
            return

        # Type-specific extra configuration (monitor/window pickers, file
        # pickers, etc.)
        if source_id in ("monitor_capture", "display_capture"):
            chosen = pick_list_property(self.root, src, "monitor_id",
                                         "Pick a monitor")
            if chosen is None:
                try: src.release()
                except Exception: pass
                return
            src.update({"monitor_id": chosen})
        elif source_id in ("window_capture", "game_capture"):
            chosen = pick_list_property(self.root, src, "window",
                                         "Pick a window")
            if chosen is None:
                try: src.release()
                except Exception: pass
                return
            src.update({"window": chosen})
        elif source_id == "image_source":
            path = filedialog.askopenfilename(
                title="Pick an image",
                filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.gif *.tga *.webp"),
                           ("All", "*.*")],
            )
            if not path:
                try: src.release()
                except Exception: pass
                return
            src.update({"file": path})
        elif source_id == "ffmpeg_source":
            path = filedialog.askopenfilename(
                title="Pick a media file",
                filetypes=[("Media", "*.mp4 *.mkv *.mov *.mp3 *.wav *.flac"),
                           ("All", "*.*")],
            )
            if not path:
                try: src.release()
                except Exception: pass
                return
            src.update({"local_file": path, "is_local_file": True})

        item = scene_entry["scene"].add(src)
        scene_entry["items"].append({"name": src.name, "source": src,
                                      "item": item, "visible": True})
        self._refresh_sources_list()
        self.sources_list.selection_clear(0, "end")
        self.sources_list.selection_set(len(scene_entry["items"]) - 1)
        self._rebuild_mixer()

    def _remove_source(self) -> None:
        entry = self._current_scene()
        if entry is None:
            return
        sel = self.sources_list.curselection()
        if not sel:
            return
        idx = sel[0]
        ie = entry["items"].pop(idx)
        try: ie["item"].remove()
        except Exception: pass
        self._refresh_sources_list()
        self._rebuild_mixer()

    def _reorder(self, delta: int) -> None:
        entry = self._current_scene()
        if entry is None:
            return
        sel = self.sources_list.curselection()
        if not sel:
            return
        i = sel[0]
        j = i + delta
        items = entry["items"]
        if not (0 <= j < len(items)):
            return
        items[i], items[j] = items[j], items[i]
        try:
            items[j]["item"].order_position = len(items) - 1 - j
        except Exception:
            pass
        self._refresh_sources_list()
        self.sources_list.selection_set(j)

    def _toggle_visibility(self) -> None:
        entry = self._current_scene()
        if entry is None:
            return
        sel = self.sources_list.curselection()
        if not sel:
            return
        ie = entry["items"][sel[0]]
        try:
            ie["item"].visible = not ie["item"].visible
            ie["visible"] = ie["item"].visible
        except Exception:
            pass
        self._refresh_sources_list()
        self.sources_list.selection_set(sel[0])

    def _on_source_select(self, _e=None) -> None:
        pass   # placeholder — could show a properties panel here

    def _refresh_sources_list(self) -> None:
        self.sources_list.delete(0, "end")
        entry = self._current_scene()
        if entry is None:
            return
        for ie in entry["items"]:
            tag = "  " if ie.get("visible", True) else "✗ "
            self.sources_list.insert("end", tag + ie["name"])

    # ------------------------------------------------------------------
    # Mixer
    # ------------------------------------------------------------------
    def _rebuild_mixer(self) -> None:
        """Rebuild MixerRows for every audio-capable source in the current scene."""
        # Tear down old rows
        for row in self.mixer_rows:
            row.cleanup()
            row.destroy()
        self.mixer_rows.clear()

        entry = self._current_scene()
        if entry is None:
            return
        # Filter to sources that report audio output (output_flags bit 2)
        # — we exposed get_output_flags via Source. Cheap fall-back: try any.
        for ie in entry["items"]:
            src = ie["source"]
            try:
                flags = get_lib().obs_source_get_output_flags(src._ptr)
                if not (flags & 2):  # OBS_SOURCE_AUDIO
                    continue
            except Exception:
                continue
            row = MixerRow(self.mixer_host, src)
            row.pack(fill="x", pady=2)
            self.mixer_rows.append(row)

    def _tick_mixer(self) -> None:
        for row in self.mixer_rows:
            try: row.update_ui()
            except tk.TclError: pass
        self.root.after(60, self._tick_mixer)

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------
    def _browse(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".mkv",
            initialfile="recording.mkv",
            filetypes=[("Matroska", "*.mkv"), ("MP4", "*.mp4"),
                       ("All files", "*.*")],
        )
        if path:
            self.path_var.set(path)

    def _start_recording(self) -> None:
        if self.obs is None:
            return
        path = self.path_var.get().strip()
        if not path:
            return
        try:
            self.output = Output.create("ffmpeg_muxer", "rec", {"path": path})
            self.output.set_video_encoder(self.venc)
            self.output.set_audio_encoder(self.aenc)
            if not self.output.start():
                err = self.output.last_error or "(no error message)"
                self.output.release()
                self.output = None
                messagebox.showerror("Recording failed", err)
                return
        except Exception as e:
            messagebox.showerror("Recording error", repr(e))
            return
        self.rec_btn.state(["disabled"])
        self.stop_btn.state(["!disabled"])

    def _stop_recording(self) -> None:
        if self.output is None:
            return
        self.output.stop(wait=True)
        self.output = None
        self.rec_btn.state(["!disabled"])
        self.stop_btn.state(["disabled"])

    # ------------------------------------------------------------------
    # Properties editor
    # ------------------------------------------------------------------
    def _open_properties(self) -> None:
        entry = self._current_scene()
        if entry is None:
            return
        sel = self.sources_list.curselection()
        if not sel:
            messagebox.showinfo("No source", "Select a source first.")
            return
        ie = entry["items"][sel[0]]
        PropertiesDialog(self.root, ie["source"], ie["item"])

    # ------------------------------------------------------------------
    # Streaming
    # ------------------------------------------------------------------
    def _on_preset_change(self, _ev=None) -> None:
        name = self.preset_var.get()
        url = STREAMING_PRESETS.get(name, "")
        # Don't blank a user-typed Custom URL
        if name != "Custom" or not self.stream_url_var.get():
            self.stream_url_var.set(url)

    def _start_streaming(self) -> None:
        if self.stream_output is not None:
            return
        if self.obs is None:
            return
        server = self.stream_url_var.get().strip()
        key    = self.stream_key_var.get().strip()
        if not server:
            messagebox.showwarning("Missing server",
                                   "Enter an RTMP server URL.")
            return
        if not key:
            messagebox.showwarning("Missing stream key",
                                   "Enter the stream key from your platform "
                                   "(YouTube Studio / Twitch dashboard / etc.).")
            return

        try:
            # 1. Service — encapsulates RTMP destination
            self.stream_service = Service.create(
                "rtmp_custom", "studio_svc",
                {"server": server, "key": key},
            )

            # 2. Encoders — CBR for streaming (live needs constant bitrate)
            self.stream_venc = VideoEncoder.create(
                "obs_x264", "stream_v",
                {
                    "rate_control": "CBR",
                    "bitrate":       4500,    # 4500 kbps — 1080p30 sweet spot
                    "keyint_sec":    2,       # 2-second keyframe interval
                    "preset":        "veryfast",
                    "profile":       "high",
                },
            )
            self.stream_aenc = AudioEncoder.create(
                "ffmpeg_aac", "stream_a", {"bitrate": 160},
            )

            # 3. Output — bind encoders + service, configure reconnect
            self.stream_output = Output.create("rtmp_output", "stream", {})
            self.stream_output.set_video_encoder(self.stream_venc)
            self.stream_output.set_audio_encoder(self.stream_aenc)
            self.stream_output.set_service(self.stream_service)
            self.stream_output.set_reconnect_settings(retry_count=20,
                                                      retry_sec=10)

            if not self.stream_output.start():
                err = self.stream_output.last_error or "(no error message)"
                self._tear_down_stream()
                messagebox.showerror("Streaming failed", err)
                return
        except Exception as e:
            self._tear_down_stream()
            messagebox.showerror("Streaming error", repr(e))
            return

        self.stream_btn.state(["disabled"])
        self.stream_stop_btn.state(["!disabled"])

    def _stop_streaming(self) -> None:
        if self.stream_output is None:
            return
        try:
            self.stream_output.stop(wait=True)
        except Exception:
            pass
        self._tear_down_stream()
        self.stream_btn.state(["!disabled"])
        self.stream_stop_btn.state(["disabled"])

    def _tear_down_stream(self) -> None:
        """Release the streaming pipeline (output, encoders, service) so we
        can re-create them cleanly for the next session."""
        for attr in ("stream_output", "stream_venc", "stream_aenc",
                     "stream_service"):
            obj = getattr(self, attr)
            if obj is not None:
                try: obj.release()
                except Exception: pass
                setattr(self, attr, None)

    # ------------------------------------------------------------------
    # Status tick
    # ------------------------------------------------------------------
    def _tick_status(self) -> None:
        parts: list[str] = []
        if self.output is not None and self.output.active:
            parts.append(
                f"● REC  frames={self.output.total_frames}  "
                f"bytes={self.output.total_bytes:,}  "
                f"dropped={self.output.frames_dropped}"
            )
        if self.stream_output is not None and self.stream_output.active:
            kbps = 0
            try:
                # crude live bitrate: bytes since previous tick → kbps
                kbps = int(self.stream_output.total_bytes * 8 / 1000 /
                            max(1, self.stream_output.total_frames / FPS))
            except Exception:
                pass
            tag = "🔴 LIVE" if not self.stream_output.reconnecting else "↻ RECON"
            parts.append(
                f"{tag}  congestion={self.stream_output.congestion:.2f}  "
                f"dropped={self.stream_output.frames_dropped}"
            )
        if parts:
            self.status_var.set("   |   ".join(parts))
        elif self.obs is not None and self.obs.initialized:
            n_scenes = len(self.scenes)
            n_sources = len(self._current_scene()["items"]) if self._current_scene() else 0
            self.status_var.set(
                f"Idle  •  {n_scenes} scene{'s' if n_scenes != 1 else ''}  "
                f"•  {n_sources} source{'s' if n_sources != 1 else ''}  "
                f"in current scene"
            )
        self.root.after(250, self._tick_status)

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------
    def _on_close(self) -> None:
        try:
            if self.output is not None and self.output.active:
                self.output.stop(wait=True)
            if self.stream_output is not None and self.stream_output.active:
                self.stream_output.stop(wait=True)
            self._tear_down_stream()
            for row in self.mixer_rows:
                row.cleanup()
            if self.display is not None:
                self.display.release()
            if self.obs is not None:
                self.obs.shutdown()
        except Exception:
            pass
        self.root.destroy()


def main() -> int:
    root = tk.Tk()
    try:
        # Modern theme on Windows; ignored elsewhere
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass
    PylibobsStudio(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
