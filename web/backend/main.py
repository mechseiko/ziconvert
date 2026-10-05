"""FastAPI web backend for ziconvert.

Wraps the shared core/ engine so a browser can call it without installing
the desktop app.  The frontend at web/frontend/ proxies requests here.

Start with::

    cd web/backend
    uvicorn main:app --reload --port 8000

Or use the provided ``web/run.bat`` / ``web/run.sh`` to launch both tiers.
"""

from __future__ import annotations

import io
import sys
from dataclasses import replace
from pathlib import Path

# ---------------------------------------------------------------------------
# Path bootstrap — make core/ importable when running from web/backend/
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent          # web/backend/
_REPO = _HERE.parent.parent                      # repo root
_CORE = _REPO / "core"

for _candidate in (_CORE,):
    _entry = str(_candidate)
    if _candidate.is_dir() and _entry not in sys.path:
        sys.path.insert(0, _entry)

# ---------------------------------------------------------------------------
# Imports — must come after path bootstrap
# ---------------------------------------------------------------------------
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from img2dxf import DXF_VERSIONS, PRESETS, SR_BACKENDS, TraceParams, run
from img2dxf.preprocess import decode_image
from img2dxf.export_dxf import build_document

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="ziconvert Web API",
    description=(
        "HTTP wrapper around the ziconvert core tracing engine. "
        "Upload an image, receive a DXF."
    ),
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "Content-Disposition",
        "X-Path-Count",
        "X-Vertex-Count",
        "X-Arc-Count",
        "X-Width-Mm",
        "X-Height-Mm",
        "X-Sr-Used",
        "X-Summary",
    ],
)

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    """Liveness check — returns 200 when the service is up."""
    return {"status": "ok", "engine_version": "0.2.0"}


@app.get("/presets")
async def list_presets():
    """Return the available preset names so the frontend can populate a dropdown."""
    return {"presets": list(PRESETS.keys())}


@app.post("/convert")
async def convert(
    file: UploadFile = File(..., description="PNG, JPEG or BMP image to trace"),
    width_mm: float = Form(100.0, description="Target output width in millimetres"),
    preset: str = Form("Logo / clipart", description="Starting parameter set"),
    denoise: bool = Form(True, description="Run bilateral denoise before thresholding"),
    morphology: bool = Form(True, description="Run morphological close+open on the mask"),
    shape_fit: bool = Form(True, description="Snap near-primitive contours to ideal shapes"),
    vector_snap: bool = Form(True, description="Snap near-H/V lines and right angles"),
    straighten: bool = Form(True, description="Flatten structurally straight runs"),
    sr_backend: str = Form("off", description="Super-resolution before tracing"),
    sr_model: str | None = Form(None, description="Model file for the sr backend"),
    snap_axis_deg: float | None = Form(None, description="Override: axis-snap tolerance, degrees"),
    snap_merge_mm: float | None = Form(None, description="Override: coordinate merge tolerance, mm"),
    snap_right_angle_deg: float | None = Form(None, description="Override: right-angle tolerance, degrees"),
    snap_circle_mm: float | None = Form(None, description="Override: circle-claim tolerance, mm"),
    dxf_version: str = Form("R2010", description="DXF format version (R2010, R2000, R12)"),
):
    """Convert an uploaded image to a DXF file.

    Returns the DXF as an attachment download.  On validation errors, returns
    a 422 with a JSON body describing the problem.
    """
    # ── Validate inputs ──────────────────────────────────────────────────
    if file.content_type and not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=422,
            detail=f"Expected an image file, got '{file.content_type}'.",
        )
    if sr_backend not in SR_BACKENDS:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown sr_backend '{sr_backend}'. Choose from: {', '.join(SR_BACKENDS)}.",
        )
    if dxf_version not in DXF_VERSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown dxf_version '{dxf_version}'. Choose from: {', '.join(DXF_VERSIONS)}.",
        )
    # Normalize preset name to match PRESETS keys
    resolved_preset = None
    if preset in PRESETS:
        resolved_preset = preset
    else:
        preset_lower = preset.strip().lower()
        alias_map = {
            "logo": "Logo / clipart",
            "logo / clipart": "Logo / clipart",
            "photo": "Photo",
            "line art": "Line art / scan",
            "line art / scan": "Line art / scan",
            "edge outline": "Edge outline",
        }
        if preset_lower in alias_map:
            resolved_preset = alias_map[preset_lower]
        else:
            for k in PRESETS:
                if k.lower() == preset_lower or k.lower().startswith(preset_lower):
                    resolved_preset = k
                    break

    if resolved_preset is None:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unknown preset '{preset}'. "
                f"Choose from: {', '.join(PRESETS.keys())}."
            ),
        )
    preset = resolved_preset
    if width_mm <= 0:
        raise HTTPException(status_code=422, detail="width_mm must be positive.")

    img_bytes = await file.read()
    if not img_bytes:
        raise HTTPException(status_code=422, detail="Uploaded file is empty.")

    # ── Decode image ─────────────────────────────────────────────────────
    try:
        rgb = decode_image(img_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # ── Build parameters ──────────────────────────────────────────────────
    base: TraceParams = PRESETS[preset]
    params = base

    # Apply web-side toggles on top of the preset.
    params = params.with_denoise(denoise)
    params = params.with_morphology(morphology)

    overrides: dict = {
        "width_mm": width_mm,
        "shape_fit": shape_fit,
        "vector_snap": vector_snap,
        "dxf_version": dxf_version,
        "sr_backend": sr_backend,
    }
    if sr_model is not None:
        overrides["sr_model"] = sr_model
    if not straighten:
        overrides["straighten_mm"] = 0.0
    # Tolerance overrides: an omitted field keeps the preset's value.
    for field, value in (
        ("snap_axis_deg", snap_axis_deg),
        ("snap_merge_mm", snap_merge_mm),
        ("snap_right_angle_deg", snap_right_angle_deg),
        ("snap_circle_mm", snap_circle_mm),
    ):
        if value is not None:
            overrides[field] = value
    params = replace(params, **overrides)

    # ── Run the engine ───────────────────────────────────────────────────
    try:
        result = run(rgb, params)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"Conversion failed: {exc}",
        ) from exc

    if result.bounds is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "No paths found in the image. "
                "Try adjusting the threshold, mode, or minimum area."
            ),
        )

    # ── Build DXF in memory ──────────────────────────────────────────────
    try:
        doc = build_document(result.paths, params)
        buf = io.StringIO()
        doc.write(buf)
        dxf_text = buf.getvalue()
        dxf_bytes = dxf_text.encode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"DXF serialisation failed: {exc}",
        ) from exc

    filename = Path(file.filename or "output").stem + ".dxf"
    return Response(
        content=dxf_bytes,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Path-Count": str(result.path_count),
            "X-Vertex-Count": str(result.vertex_count),
            "X-Arc-Count": str(result.arc_count),
            "X-Width-Mm": f"{result.bounds.width:.2f}",
            "X-Height-Mm": f"{result.bounds.height:.2f}",
            "X-Sr-Used": result.sr_used,
            "X-Summary": result.summary(),
        },
    )


@app.get("/")
async def root():
    """API root — describes available endpoints."""
    return {
        "service": "ziconvert Web API",
        "version": "0.2.0",
        "endpoints": {
            "GET  /health": "Liveness check",
            "GET  /presets": "List available presets",
            "POST /convert": "Convert image → DXF",
        },
        "docs": "/docs",
    }
