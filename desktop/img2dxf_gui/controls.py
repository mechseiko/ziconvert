"""The parameter panel: Tk variables in, :class:`TraceParams` out."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from img2dxf import settings as settings_io
from . import tooltips
from img2dxf.params import DEFAULT_PRESET, DXF_VERSIONS, PRESETS, TraceParams
from dataclasses import replace

MODES = ("otsu", "fixed", "adaptive", "posterize", "edges")

_MODE_HELP = {
    "otsu": "Automatic threshold. Best for logos, clipart and text.",
    "fixed": "Manual threshold. Use when Otsu picks the wrong level.",
    "adaptive": "Local threshold. For scans with uneven lighting.",
    "posterize": "Tone bands, one layer each. For photographs.",
    "edges": "Canny edge outlines. Detail without solid fills.",
}

#: Which controls matter for each mode, so the panel only ever offers sliders
#: that actually do something.
_MODE_FIELDS = {
    "otsu": (),
    "fixed": ("threshold",),
    "adaptive": ("adaptive_block", "adaptive_c"),
    "posterize": ("levels",),
    "edges": ("canny_low", "canny_high", "edge_dilate"),
}

_HINT_COLOR = "#555555"


class ControlPanel(ttk.Frame):
    """Left-hand column of parameter widgets."""

    def __init__(self, master, on_change: Callable[[], None]) -> None:
        super().__init__(master, padding=(10, 8))
        self._on_change = on_change
        self._suspend = False
        self._vars: dict[str, tk.Variable] = {}
        self._mode_rows: dict[str, list[tk.Widget]] = {}
        self._sections: dict[str, ttk.LabelFrame] = {}
        # The crop box is set by dragging on the preview, not by a widget, so
        # it lives here rather than in a Tk variable.
        self._crop: tuple[float, float, float, float] | None = None

        # Initialize default values
        self._vars["detail"] = tk.IntVar(value=0)
        self._vars["rotate_deg"] = tk.DoubleVar(value=0.0)
        self._vars["copies_x"] = tk.IntVar(value=1)
        self._vars["copies_y"] = tk.IntVar(value=1)
        self._vars["tile_gap_mm"] = tk.DoubleVar(value=0.0)
        self._vars["bed_width_mm"] = tk.StringVar(value="0")
        self._vars["bed_height_mm"] = tk.StringVar(value="0")
        self._vars["size_mode"] = tk.StringVar(value="fit")
        self._vars["width_mm"] = tk.StringVar(value="100")
        self._vars["dpi"] = tk.StringVar(value="96")
        self._vars["dxf_version"] = tk.StringVar(value="R2010")

        self._build()
        self.apply_preset(DEFAULT_PRESET)

    # -- construction ---------------------------------------------------

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)

        ttk.Label(self, text="Laser Cut Optimized", font=("TkDefaultFont", 10, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 8))

        self._image_section(1)
        self._size_section(2)
        self._output_section(3)

    def _image_section(self, row: int) -> None:
        frame = self._section("Image", row)

        self._slider(frame, 0, "rotate_deg", "Rotate", -180, 180, decimals=1)
        self._detail_row(frame, 4)

        buttons = ttk.Frame(frame)
        buttons.grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 0))
        tooltips.attach(
            buttons, "Turn the image a quarter turn at a time, or back upright."
        )
        for label, delta in (("-90", -90), ("0", None), ("+90", 90)):
            ttk.Button(
                buttons, text=label, width=5,
                command=lambda d=delta: self._nudge_rotation(d),
            ).pack(side="left", padx=(0, 4))

        ttk.Label(
            frame,
            text="Drag on the preview with Crop enabled to frame the artwork.",
            wraplength=240, foreground=_HINT_COLOR,
        ).grid(row=2, column=0, columnspan=3, sticky="w")

    def _detail_row(self, frame, row: int) -> None:
        """Supersampling. Auto is the default and suits almost everything."""
        self._vars["detail"] = tk.IntVar(value=0)
        ttk.Label(frame, text="Detail").grid(row=row, column=0, sticky="w")

        box = ttk.Frame(frame)
        box.grid(row=row, column=1, columnspan=2, sticky="w", pady=2)
        for label, value in (("Auto", 0), ("1x", 1), ("2x", 2), ("3x", 3), ("4x", 4)):
            ttk.Radiobutton(
                box, text=label, value=value,
                variable=self._vars["detail"], command=self._changed,
            ).pack(side="left")
        tooltips.attach_children(box, tooltips.HELP["detail"])

        ttk.Label(
            frame,
            text=(
                "Traces an upscaled copy. Thresholding is what limits edge "
                "quality, and this is the only control that lifts it."
            ),
            wraplength=240, foreground=_HINT_COLOR,
        ).grid(row=row + 1, column=0, columnspan=3, sticky="w")

    def _nudge_rotation(self, delta: float | None) -> None:
        """Step by 90 degrees, or reset to upright when ``delta`` is None."""
        var = self._vars["rotate_deg"]
        value = 0.0 if delta is None else _wrap_degrees(var.get() + delta)
        var.set(value)
        self._changed()

    def _layout_section(self, row: int) -> None:
        frame = self._section("Layout", row)

        self._slider(frame, 0, "copies_x", "Copies across", 1, 12)
        self._slider(frame, 1, "copies_y", "Copies down", 1, 12)
        self._slider(frame, 2, "tile_gap_mm", "Tile gap (mm)", 0.0, 20.0, decimals=1)

        bed = ttk.Frame(frame)
        bed.grid(row=3, column=0, columnspan=3, sticky="w", pady=(4, 0))
        ttk.Label(bed, text="Bed (mm)").pack(side="left", padx=(0, 6))
        self._vars["bed_width_mm"] = tk.StringVar(value="0")
        self._vars["bed_height_mm"] = tk.StringVar(value="0")
        for field in ("bed_width_mm", "bed_height_mm"):
            entry = ttk.Entry(bed, textvariable=self._vars[field], width=6)
            entry.pack(side="left", padx=(0, 4))
            entry.bind("<Return>", lambda _e: self._changed())
            entry.bind("<FocusOut>", lambda _e: self._changed())
            tooltips.attach_field(entry, "bed_width_mm")
        tooltips.attach(bed, tooltips.HELP["bed_width_mm"])

        ttk.Label(
            frame,
            text="Set your machine's bed to get a fit warning. 0 disables it.",
            wraplength=240, foreground=_HINT_COLOR,
        ).grid(row=4, column=0, columnspan=3, sticky="w")

    def _size_section(self, row: int) -> None:
        frame = self._section("Size", row)

        self._vars["size_mode"] = tk.StringVar(value="fit")
        for column, (label, value) in enumerate(
            (("Fit to width", "fit"), ("Use image DPI", "dpi"))
        ):
            button = ttk.Radiobutton(
                frame,
                text=label,
                value=value,
                variable=self._vars["size_mode"],
                command=self._changed,
            )
            button.grid(row=0, column=column, sticky="w", pady=2)
            tooltips.attach_field(button, "size_mode")

        self._entry(frame, 1, "width_mm", "Width (mm)", "100")
        self._entry(frame, 2, "dpi", "DPI", "96")

    def _output_section(self, row: int) -> None:
        frame = self._section("Output", row)

        self._vars["dxf_version"] = tk.StringVar(value="R2010")
        ttk.Label(frame, text="DXF version").grid(row=0, column=0, sticky="w")
        version = ttk.Combobox(
            frame,
            textvariable=self._vars["dxf_version"],
            values=list(DXF_VERSIONS),
            state="readonly",
            width=10,
        )
        version.grid(row=0, column=1, sticky="w", pady=2)
        version.bind("<<ComboboxSelected>>", lambda _e: self._changed())
        tooltips.attach_field(version, "dxf_version")

        self._entry(frame, 1, "layer_name", "Layer", "CUT")
        ttk.Label(
            frame,
            text="R12 for older RDWorks/LaserCAD; R2010 for LightBurn.",
            wraplength=230,
            foreground=_HINT_COLOR,
        ).grid(row=2, column=0, columnspan=3, sticky="w")

    # -- widget helpers -------------------------------------------------

    def _section(self, title: str, row: int) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(self, text=title, padding=(8, 4))
        frame.grid(row=row, column=0, sticky="ew", pady=4)
        frame.columnconfigure(1, weight=1)
        self._sections[title] = frame
        return frame

    def _slider(
        self, parent, row, field, label, low, high, *, decimals=0, step=1
    ) -> None:
        is_float = decimals > 0
        var: tk.Variable = tk.DoubleVar() if is_float else tk.IntVar()
        self._vars[field] = var
        readout = tk.StringVar()

        def on_move(_value=None) -> None:
            raw = var.get()
            if not is_float:
                snapped = int(round(raw / step) * step)
                if snapped != raw:
                    var.set(snapped)
                raw = snapped
            readout.set(f"{raw:.{decimals}f}")
            self._changed()

        name = ttk.Label(parent, text=label)
        name.grid(row=row, column=0, sticky="w")

        scale = ttk.Scale(
            parent,
            from_=low,
            to=high,
            variable=var,
            orient="horizontal",
            command=on_move,
        )
        scale.grid(row=row, column=1, sticky="ew", padx=4, pady=1)

        value = ttk.Label(parent, textvariable=readout, width=5, anchor="e")
        value.grid(row=row, column=2, sticky="e")

        # The label is the easiest thing to hover, so it gets help too.
        for widget in (name, scale, value):
            tooltips.attach_field(widget, field)

    def _checkbox(self, parent, row, field, label, *, default=False) -> None:
        var = tk.BooleanVar(value=default)
        self._vars[field] = var
        box = ttk.Checkbutton(
            parent, text=label, variable=var, command=self._changed
        )
        box.grid(row=row, column=0, columnspan=3, sticky="w", pady=2)
        tooltips.attach_field(box, field)

    def _entry(self, parent, row, field, label, default) -> None:
        var = tk.StringVar(value=default)
        self._vars[field] = var
        name = ttk.Label(parent, text=label)
        name.grid(row=row, column=0, sticky="w")
        entry = ttk.Entry(parent, textvariable=var, width=10)
        entry.grid(row=row, column=1, sticky="w", pady=2)
        for widget in (name, entry):
            tooltips.attach_field(widget, field)
        # Retrace on Enter or focus-out rather than per keystroke, so a
        # half-typed "1" in "100" never triggers a run at 1 mm.
        entry.bind("<Return>", lambda _e: self._changed())
        entry.bind("<FocusOut>", lambda _e: self._changed())

    # -- state ----------------------------------------------------------

    def _changed(self) -> None:
        if not self._suspend:
            self._on_change()

    def set_params(self, params: TraceParams, *, framing: bool = False) -> None:
        """Load a whole parameter set into the widgets."""
        self._suspend = True
        try:
            for field, var in self._vars.items():
                value = getattr(params, field, None)
                if value is not None:
                    var.set(value)
            if framing:
                self._crop = params.crop
        finally:
            self._suspend = False
        self._changed()

    def crop(self) -> tuple[float, float, float, float] | None:
        """The crop box currently applied, in fractions of the source image."""
        return self._crop

    def set_field(self, field: str, value) -> None:
        """Set one control without triggering a re-trace."""
        if field == "crop":
            self._crop = value
            self._crop_label.configure(text=_describe_crop(value))
            return

        var = self._vars.get(field)
        if var is None:
            return
        self._suspend = True
        try:
            var.set(value)
        finally:
            self._suspend = False

    def params(self) -> TraceParams:
        """Read the widgets back into a :class:`TraceParams`."""
        values = {field: var.get() for field, var in self._vars.items()}
        base = PRESETS[DEFAULT_PRESET]
        return replace(
            base,
            detail=int(values.get("detail", 0)),
            rotate_deg=float(values.get("rotate_deg", 0.0)),
            crop=self._crop,
            copies_x=int(values.get("copies_x", 1)),
            copies_y=int(values.get("copies_y", 1)),
            tile_gap_mm=float(values.get("tile_gap_mm", 0.0)),
            bed_width_mm=_number(values.get("bed_width_mm", "0"), 0.0, allow_zero=True),
            bed_height_mm=_number(values.get("bed_height_mm", "0"), 0.0, allow_zero=True),
            size_mode=values.get("size_mode", "fit"),
            width_mm=_number(values.get("width_mm", "100"), 100.0),
            dpi=_number(values.get("dpi", "96"), 96.0),
            dxf_version=values.get("dxf_version", "R2010"),
        ).normalized()


def _wrap_degrees(value: float) -> float:
    """Keep rotation in -180..180 so the slider handle stays where expected."""
    wrapped = (float(value) + 180.0) % 360.0 - 180.0
    return round(wrapped, 1)


def _describe_crop(box) -> str:
    if box is None:
        return "Crop: whole image"
    left, top, right, bottom = box
    return f"Crop: {(right - left) * 100:.0f}% x {(bottom - top) * 100:.0f}%"


def _number(raw, fallback: float, *, allow_zero: bool = False) -> float:
    """Parse a text entry, falling back rather than throwing mid-edit.

    ``allow_zero`` is for fields where zero means "off" rather than "invalid",
    such as the bed size.
    """
    try:
        value = float(str(raw).replace(",", "."))
    except (TypeError, ValueError):
        return fallback
    if value > 0 or (allow_zero and value == 0):
        return value
    return fallback
