"""img2dxf — turn PNG/JPEG images into laser-ready DXF contour outlines."""

from .export_dxf import write_dxf
from .geometry import Bounds, Path
from .params import DXF_VERSIONS, PRESETS, TraceParams
from .pipeline import TraceResult, run, run_file
from .shape_fit import PrimitiveFit, PrimitiveKind, fit_primitive

__version__ = "0.1.0"

__all__ = [
    "Bounds",
    "DXF_VERSIONS",
    "PRESETS",
    "Path",
    "PrimitiveFit",
    "PrimitiveKind",
    "TraceParams",
    "TraceResult",
    "fit_primitive",
    "run",
    "run_file",
    "write_dxf",
]
