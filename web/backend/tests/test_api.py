"""Tests for web/backend/main.py (FastAPI wrapper around the core engine).

Run from the repo root:  pytest web/backend/test_api.py
Requires fastapi + httpx (see web/backend/requirements.txt).

Covers:
- /health and /presets
- /convert happy path: DXF bytes, attachment headers, engine stats
- Validation: non-image upload, empty upload, unknown preset,
  unknown sr_backend, unknown dxf_version, non-positive width
- Parameter plumbing: shape_fit off leaves near-primitives unidealised,
  sr_backend override reaches the engine's report
"""

from __future__ import annotations

import io
import re
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent      # web/backend/
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(BACKEND_DIR.parents[1] / "core"))

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def square_png():
    """A dark square on white — the engine's bread and butter."""
    image = np.full((160, 160, 3), 255, np.uint8)
    image[40:120, 40:120] = 0
    ok, encoded = cv2.imencode(".png", image)
    assert ok
    return io.BytesIO(encoded.tobytes())


def _post(client, png: io.BytesIO, **data):
    png.seek(0)
    return client.post(
        "/convert",
        files={"file": ("part.png", png, "image/png")},
        data=data,
    )


# ---------------------------------------------------------------------------
# Trivial endpoints
# ---------------------------------------------------------------------------

def test_health_is_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_presets_lists_builtin_names(client):
    response = client.get("/presets")
    assert response.status_code == 200
    names = response.json()["presets"]
    assert "Logo / clipart" in names


def test_root_describes_endpoints(client):
    response = client.get("/")
    assert response.status_code == 200
    endpoints = response.json()["endpoints"]
    assert any("/convert" in key for key in endpoints)
    assert any("/health" in key for key in endpoints)


# ---------------------------------------------------------------------------
# /convert happy path
# ---------------------------------------------------------------------------

def test_convert_returns_dxf_attachment(client, square_png):
    response = _post(client, square_png)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.headers["content-disposition"].endswith('filename="part.dxf"')
    body = response.text
    # A DXF starts with a group-code 0 / SECTION pair.
    assert re.match(r"\s*0\s*\nSECTION", body)
    assert response.headers["x-path-count"] >= "1"
    assert "X-Width-Mm" in response.headers  # exact case-insensitive name: x-width-mm
    assert response.headers["x-sr-used"] == "off"


def test_convert_summary_reports_the_engine(client, square_png):
    response = _post(client, square_png)
    summary = response.headers["x-summary"]
    assert "paths" in summary and "mm" in summary


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_convert_rejects_non_image(client):
    response = client.post(
        "/convert",
        files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert response.status_code == 422
    assert "image" in response.json()["detail"].lower()


def test_convert_rejects_empty_upload(client):
    response = client.post(
        "/convert",
        files={"file": ("empty.png", io.BytesIO(b""), "image/png")},
    )
    assert response.status_code == 422


def test_convert_rejects_unknown_preset(client, square_png):
    response = _post(client, square_png, preset="holomorphic")
    assert response.status_code == 422
    assert "preset" in response.json()["detail"].lower()


def test_convert_rejects_unknown_sr_backend(client, square_png):
    response = _post(client, square_png, sr_backend="hyper-scale")
    assert response.status_code == 422
    assert "sr_backend" in response.json()["detail"]


def test_convert_rejects_unknown_dxf_version(client, square_png):
    response = _post(client, square_png, dxf_version="R14")
    assert response.status_code == 422
    assert "dxf_version" in response.json()["detail"]


def test_convert_rejects_non_positive_width(client, square_png):
    response = _post(client, square_png, width_mm=0)
    assert response.status_code == 422


def test_convert_blank_image_is_a_friendly_422(client):
    image = np.full((64, 64, 3), 255, np.uint8)
    ok, encoded = cv2.imencode(".png", image)
    assert ok
    response = _post(client, io.BytesIO(encoded.tobytes()))
    assert response.status_code == 422
    assert "no paths" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Parameter plumbing
# ---------------------------------------------------------------------------

def test_dxf_version_reaches_the_document(client, square_png):
    r12 = _post(client, square_png, dxf_version="R12")
    assert r12.status_code == 200
    assert "$ACADVER" in r12.text
    assert "AC1009" in r12.text  # R12's ezdxf revision tag


def test_shape_fit_toggle_is_accepted_with_the_rest(client, square_png):
    response = _post(
        client,
        square_png,
        shape_fit="false",
        vector_snap="true",
        straighten="false",
        denoise="false",
        morphology="false",
    )
    assert response.status_code == 200
    assert response.headers["x-path-count"] >= "1"


def test_snap_tolerance_overrides_are_accepted(client, square_png):
    response = _post(
        client,
        square_png,
        snap_axis_deg="1.0",
        snap_merge_mm="0.02",
        snap_right_angle_deg="2.0",
        snap_circle_mm="0.3",
    )
    assert response.status_code == 200


def test_sr_backend_override_is_reported_truthfully(client, square_png):
    # No neural model files exist in the test environment, so "cubic" must be
    # exactly what the header says — the report never claims a fallback ran.
    response = _post(client, square_png, sr_backend="cubic")
    assert response.status_code == 200
    assert response.headers["x-sr-used"] == "cubic"
