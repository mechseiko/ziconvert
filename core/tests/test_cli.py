"""Tests for core/img2dxf/cli.py.

Covers:
- params_from_args folding: sr flags, snap flags, denoise/morph flags,
  the no-* switches, kerf side defaulting, dpi sizing, crop and copies
- Presets: built-ins listed, unknown preset rejected
- main() end to end: PNG to DXF and to SVG, output extension inference,
  missing image, empty result warning
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from img2dxf.cli import (
    _format_from,
    _parse_crop,
    all_presets,
    build_parser,
    main,
    params_from_args,
)


def _parse(argv: list[str]):
    return params_from_args(build_parser().parse_args(argv))


# ---------------------------------------------------------------------------
# Flag folding
# ---------------------------------------------------------------------------

def test_sr_flags_fold_into_params():
    params = _parse(["in.png", "--sr", "dnn", "--sr-model", "FSRCNN_x2.pb"])
    assert params.sr_backend == "dnn"
    assert params.sr_model == "FSRCNN_x2.pb"


def test_sr_rejects_unknown_backend():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["in.png", "--sr", "warp-drive"])


def test_snap_flags_fold_into_params():
    params = _parse(
        [
            "in.png",
            "--snap-axis-deg", "1.5",
            "--snap-merge", "0.08",
            "--snap-right-angle-deg", "2.0",
            "--snap-circle", "0.4",
        ]
    )
    assert params.snap_axis_deg == 1.5
    assert params.snap_merge_mm == 0.08
    assert params.snap_right_angle_deg == 2.0
    assert params.snap_circle_mm == 0.4


def test_no_vector_snap_disables_the_pass():
    assert _parse(["in.png", "--no-vector-snap"]).vector_snap is False
    assert _parse(["in.png"]).vector_snap is True


def test_denoise_and_morph_flags_fold_into_params():
    params = _parse(
        [
            "in.png",
            "--denoise", "7",
            "--denoise-mode", "bilateral",
            "--bilateral-sigma-color", "40",
            "--nlm-h", "4",
            "--close", "2",
            "--open", "1",
            "--morph-kernel", "rect",
            "--morph-iterations", "3",
        ]
    )
    assert params.denoise == 7
    assert params.denoise_mode == "bilateral"
    assert params.bilateral_sigma_color == 40
    assert params.nlm_h == 4
    assert params.close_px == 2
    assert params.open_px == 1
    assert params.morph_kernel == "rect"
    assert params.morph_iterations == 3


def test_switches_flip_the_obvious_params():
    params = _parse(
        [
            "in.png",
            "--no-denoise",
            "--no-shape-fit",
            "--no-arcs",
            "--no-straighten",
            "--no-holes",
            "--center",
            "--auto-levels",
            "--no-order",
        ]
    )
    assert params.denoise == 0
    assert params.shape_fit is False
    assert params.fit_arcs is False
    assert params.straighten_mm == 0.0
    assert params.keep_holes is False
    assert params.origin == "center"
    assert params.auto_levels is True
    assert params.optimize_order is False


def test_kerf_without_side_defaults_to_outside():
    assert _parse(["in.png", "--kerf", "0.2"]).kerf_side == "outside"
    assert _parse(["in.png", "--kerf", "0.2", "--kerf-side", "inside"]).kerf_side == "inside"


def test_dpi_selects_dpi_sizing():
    params = _parse(["in.png", "--dpi", "300"])
    assert params.size_mode == "dpi"
    assert params.dpi == 300


def test_copies_and_crop_are_parsed_as_pairs():
    params = _parse(["in.png", "--copies", "3x2", "--crop", "0.1,0,0.9,0.8"])
    assert (params.copies_x, params.copies_y) == (3, 2)
    assert params.crop == (0.1, 0.0, 0.9, 0.8)


def test_crop_parser_rejects_wrong_count():
    with pytest.raises(argparse_error()):
        _parse_crop("0.1,0.9")


def argparse_error():
    import argparse

    return argparse.ArgumentTypeError


# ---------------------------------------------------------------------------
# Presets and settings handoff
# ---------------------------------------------------------------------------

def test_all_presets_includes_builtins():
    presets = all_presets()
    assert presets, "built-in presets must exist"
    assert all(isinstance(p, type(params_from_args(build_parser().parse_args(["x"])))) for p in presets.values())


def test_unknown_preset_exits_with_available_names():
    with pytest.raises(SystemExit) as excinfo:
        _parse(["in.png", "--preset", "no-such-preset"])
    message = str(excinfo.value)
    assert "no-such-preset" in message
    assert "available:" in message


def test_settings_file_beats_defaults(tmp_path):
    from img2dxf.params import TraceParams
    from img2dxf.settings import save

    path = tmp_path / "settings.json"
    save(TraceParams(denoise_mode="nlm", snap_circle_mm=0.42), path)
    params = _parse(["in.png", "--settings", str(path)])
    assert params.denoise_mode == "nlm"
    assert params.snap_circle_mm == 0.42


def test_flag_beats_settings_file(tmp_path):
    from img2dxf.params import TraceParams
    from img2dxf.settings import save

    path = tmp_path / "settings.json"
    save(TraceParams(denoise=3), path)
    params = _parse(["in.png", "--settings", str(path), "--denoise", "9"])
    assert params.denoise == 9


# ---------------------------------------------------------------------------
# End to end
# ---------------------------------------------------------------------------

@pytest.fixture
def png(tmp_path):
    """A small dark square on white — traces to one rectangle."""
    image = np.full((120, 120, 3), 255, np.uint8)
    image[30:90, 30:90] = 0
    path = tmp_path / "part.png"
    cv2.imwrite(str(path), image)
    return path


def test_main_writes_dxf_next_to_the_image(png, capsys):
    exit_code = main([str(png)])
    assert exit_code == 0
    dxf = png.with_suffix(".dxf")
    assert dxf.is_file()
    assert "wrote" in capsys.readouterr().out


def test_main_writes_svg_when_extension_says_so(png):
    out = png.with_name("part.svg")
    exit_code = main([str(png), "-o", str(out)])
    assert exit_code == 0
    assert out.is_file()
    assert b"<svg" in out.read_bytes()[:200].lower()


def test_main_explicit_format_wins_over_extension(png, tmp_path):
    out = tmp_path / "part.txt"
    exit_code = main([str(png), "-o", str(out), "--format", "svg"])
    assert exit_code == 0
    assert out.is_file()


def test_main_missing_image_returns_two():
    assert main(["nowhere.png"]) == 2


def test_main_no_image_returns_two():
    assert main([]) == 2


def test_main_empty_result_warns_and_returns_one(png, capsys):
    # A pure-white image traces to nothing.
    blank = png.with_name("blank.png")
    cv2.imwrite(str(blank), np.full((64, 64, 3), 255, np.uint8))
    exit_code = main([str(blank)])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "empty" in captured.err


def test_list_presets_prints_names(capsys):
    assert main(["--list-presets"]) == 0
    assert capsys.readouterr().out.strip()


# ---------------------------------------------------------------------------
# Small parsers
# ---------------------------------------------------------------------------

def test_format_from_defaults_to_dxf():
    assert _format_from(None) == "dxf"
    assert _format_from(_p("x.dxf")) == "dxf"
    assert _format_from(_p("x.svg")) == "svg"
    assert _format_from(_p("x.DXF")) == "dxf"  # and any other extension


def _p(name):
    from pathlib import Path

    return Path(name)
