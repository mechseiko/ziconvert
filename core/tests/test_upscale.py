"""Tests for core/img2dxf/upscale.py.

Covers:
- factor <= 1 → image returned untouched, reported as "off"
- Classical backends (off/cubic/lanczos) resize by exactly ``factor``
- "dnn"/"auto" with no model anywhere → honest fallback to "lanczos"
- _DNN_MODEL.resolve: filename parsing, closest-scale choice, explicit path wins
- _ESRGAN_MODEL.resolve: scale parsing, missing .bin → unavailable
- _to_factor: native-scale remainder finished to the exact factor
- A corrupt model file must never fail the job — degrade and say so
- Pipeline wiring: a run with sr_backend="cubic" reports sr_used="cubic"
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import img2dxf.upscale as upscale_module
from img2dxf.params import TraceParams
from img2dxf.pipeline import run
from img2dxf.upscale import (
    _DNN_MODEL,
    _ESRGAN_MODEL,
    _esrgan_scale,
    _to_factor,
    upscale,
)

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# No upscaling wanted
# ---------------------------------------------------------------------------

def test_factor_one_returns_image_unchanged():
    image = np.zeros((40, 30, 3), np.uint8)
    out, used = upscale(image, 1, TraceParams(sr_backend="esrgan"))
    assert out is image
    assert used == "off"


def test_factor_zero_is_treated_as_no_upscaling():
    image = np.zeros((10, 10, 3), np.uint8)
    out, used = upscale(image, 0, TraceParams(sr_backend="auto"))
    assert out is image
    assert used == "off"


# ---------------------------------------------------------------------------
# Classical backends resize by exactly the factor and say so
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("backend", "expected"),
    [("off", "off"), ("cubic", "cubic"), ("lanczos", "lanczos")],
)
def test_classical_backends_resize_and_report(backend, expected):
    image = np.zeros((20, 32, 3), np.uint8)
    out, used = upscale(image, 3, TraceParams(sr_backend=backend))
    assert out.shape == (60, 96, 3)
    assert used == expected


# ---------------------------------------------------------------------------
# Neural requests without models degrade honestly
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("backend", ["dnn", "esrgan", "auto"])
def test_neural_request_without_models_falls_back_to_lanczos(
    tmp_path, monkeypatch, backend
):
    # Point the model directory at an empty place so the user's real
    # ~/.img2dxf/models cannot leak into the test result.
    monkeypatch.setattr(upscale_module, "MODEL_DIR", tmp_path / "absent")
    image = np.zeros((16, 16, 3), np.uint8)
    out, used = upscale(image, 2, TraceParams(sr_backend=backend))
    assert out.shape == (32, 32, 3)
    assert used == "lanczos"


def test_corrupt_model_file_fails_the_backend_not_the_job(tmp_path, monkeypatch):
    monkeypatch.setattr(upscale_module, "MODEL_DIR", tmp_path)
    (tmp_path / "FSRCNN_x2.pb").write_bytes(b"not a protobuf at all")
    image = np.full((16, 16, 3), 200, np.uint8)
    out, used = upscale(image, 2, TraceParams(sr_backend="dnn"))
    assert out.shape == (32, 32, 3)
    assert used == "lanczos"


def test_unparsable_model_files_are_ignored(tmp_path, monkeypatch):
    monkeypatch.setattr(upscale_module, "MODEL_DIR", tmp_path)
    (tmp_path / "mystery_model.pb").write_bytes(b"whatever")
    image = np.zeros((16, 16, 3), np.uint8)
    out, used = upscale(image, 2, TraceParams(sr_backend="dnn"))
    assert used == "lanczos"


# ---------------------------------------------------------------------------
# .pb resolution: parsing and closest-scale choice
# ---------------------------------------------------------------------------

def _fake_pb(directory, name):
    path = directory / name
    path.write_bytes(b"x")
    return path


def test_dnn_resolve_parses_family_and_scale(tmp_path, monkeypatch):
    monkeypatch.setattr(upscale_module, "MODEL_DIR", tmp_path)
    _fake_pb(tmp_path, "FSRCNN_x2.pb")
    resolved = _DNN_MODEL.resolve(2, None)
    assert resolved is not None
    family, scale, _path = resolved
    assert family == "fsrcnn"
    assert scale == 2


def test_dnn_resolve_picks_closest_scale(tmp_path, monkeypatch):
    monkeypatch.setattr(upscale_module, "MODEL_DIR", tmp_path)
    _fake_pb(tmp_path, "FSRCNN_x2.pb")
    _fake_pb(tmp_path, "EDSR_x4.pb")
    # Asking for x4 must prefer the x4 model, asking for x2 the x2 one.
    assert _DNN_MODEL.resolve(4, None)[1] == 4
    assert _DNN_MODEL.resolve(2, None)[1] == 2


def test_dnn_resolve_explicit_path_wins(tmp_path, monkeypatch):
    monkeypatch.setattr(upscale_module, "MODEL_DIR", tmp_path)
    _fake_pb(tmp_path, "EDSR_x4.pb")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    explicit = _fake_pb(elsewhere, "FSRCNN_x2.pb")
    family, scale, path = _DNN_MODEL.resolve(4, str(explicit))
    assert (family, scale) == ("fsrcnn", 2)
    assert path == explicit


def test_dnn_resolve_explicit_unparsable_path_is_ignored(tmp_path):
    stray = _fake_pb(tmp_path, "unknown_net.pb")
    assert _DNN_MODEL.resolve(2, str(stray)) is None
    assert _DNN_MODEL.resolve(2, None) is None


# ---------------------------------------------------------------------------
# ESRGAN resolution
# ---------------------------------------------------------------------------

def test_esrgan_scale_parsing():
    def named(name: str) -> Path:
        return Path(name)

    assert _esrgan_scale(named("RealESRGAN_x4plus.param")) == 4
    assert _esrgan_scale(named("realesr-general-x4v3.param")) == 4
    assert _esrgan_scale(named("realesr-net-x2v3.param")) == 2
    # No scale in the name: the family ships x4, so that is the guess.
    assert _esrgan_scale(named("RealESRGAN.param")) == 4


def test_esrgan_resolve_needs_bin_beside_param(tmp_path, monkeypatch):
    # A stub ncnn module makes the pairing logic testable whether or not the
    # real package is installed — resolve only probes ``import ncnn``.
    monkeypatch.setitem(sys.modules, "ncnn", types.ModuleType("ncnn"))
    monkeypatch.setattr(upscale_module, "MODEL_DIR", tmp_path)
    lonely = tmp_path / "RealESRGAN_x4plus.param"
    lonely.write_bytes(b"param data")
    # No .bin sibling: the pair is incomplete, the backend is unavailable.
    assert _ESRGAN_MODEL.resolve(4, None) is None

    (tmp_path / "RealESRGAN_x4plus.bin").write_bytes(b"bin data")
    resolved = _ESRGAN_MODEL.resolve(4, None)
    assert resolved is not None
    _scale, param, model_bin = resolved
    assert param == lonely
    assert model_bin == tmp_path / "RealESRGAN_x4plus.bin"


def test_esrgan_resolve_without_ncnn_is_unavailable(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "ncnn", None)  # import must fail
    monkeypatch.setattr(upscale_module, "MODEL_DIR", tmp_path)
    (tmp_path / "RealESRGAN_x4plus.param").write_bytes(b"p")
    (tmp_path / "RealESRGAN_x4plus.bin").write_bytes(b"b")
    assert _ESRGAN_MODEL.resolve(4, None) is None


# ---------------------------------------------------------------------------
# Native-scale remainder
# ---------------------------------------------------------------------------

def test_to_factor_passes_through_when_scales_match():
    image = np.zeros((8, 8, 3), np.uint8)
    assert _to_factor(image, 4, 4) is image


def test_to_factor_resizes_the_remainder():
    image = np.zeros((8, 8, 3), np.uint8)
    out = _to_factor(image, 4, 2)
    assert out.shape == (16, 16, 3)


# ---------------------------------------------------------------------------
# Pipeline wiring
# ---------------------------------------------------------------------------

def test_pipeline_reports_the_backend_that_ran():
    """sr_used must describe the pixels actually traced, not the request."""
    image = np.full((200, 200, 3), 255, np.uint8)
    image[60:140, 60:140] = 0
    params = TraceParams(
        size_mode="width",
        width_mm=100.0,
        detail=2,
        sr_backend="cubic",
    )
    result = run(image, params)
    assert result.sr_used == "cubic"
    assert result.path_count >= 1
    # And the summary line must carry it.
    assert "sr=cubic" in result.summary()


def test_pipeline_default_is_off():
    image = np.full((200, 200, 3), 255, np.uint8)
    image[60:140, 60:140] = 0
    result = run(image, TraceParams(size_mode="width", width_mm=100.0))
    assert result.sr_used == "off"
    assert "sr=" not in result.summary()
