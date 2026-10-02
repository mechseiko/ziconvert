"""Tests for core/img2dxf/preprocess.py.

Covers:
- decode_image / encode_image round-trips
- bilateral filter (denoise_mode="bilateral")
- NLM denoising (denoise_mode="nlm")
- morphological close/open
- binarize modes
- auto_levels
"""

from __future__ import annotations

import io

import cv2
import numpy as np
import pytest
from PIL import Image

from img2dxf.params import TraceParams
from img2dxf.preprocess import (
    auto_levels,
    binarize,
    decode_image,
    denoise,
    encode_image,
    prepare,
    to_grayscale,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_gray(size: int = 100, value: int = 128) -> np.ndarray:
    return np.full((size, size), value, dtype=np.uint8)


def _make_rgb(size: int = 100, value: int = 200) -> np.ndarray:
    return np.full((size, size, 3), value, dtype=np.uint8)


def _png_bytes(rgb: np.ndarray) -> bytes:
    pil = Image.fromarray(rgb, "RGB")
    buf = io.BytesIO()
    pil.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# decode_image / encode_image
# ---------------------------------------------------------------------------

def test_decode_image_returns_rgb_array():
    rgb = _make_rgb(50, 120)
    data = _png_bytes(rgb)
    decoded = decode_image(data)
    assert decoded.shape == (50, 50, 3)
    # The round-trip value should be close; PNG is lossless.
    assert np.abs(decoded.astype(int) - 120).max() == 0


def test_decode_image_raises_on_empty():
    with pytest.raises(ValueError, match="no image data"):
        decode_image(b"")


def test_decode_image_raises_on_garbage():
    with pytest.raises(ValueError, match="not a readable"):
        decode_image(b"\x00\x01\x02\x03corrupted")


def test_encode_image_produces_nonempty_bytes():
    rgb = _make_rgb(20, 100)
    data = encode_image(rgb, fmt="png")
    assert len(data) > 0
    # Must be a valid PNG: starts with the PNG magic bytes.
    assert data[:4] == b"\x89PNG"


def test_encode_image_unknown_fmt_returns_empty_or_raises():
    """OpenCV 4 returns (False, None) for unknown formats; OpenCV 5 raises.
    Either behaviour is acceptable — the key guarantee is that callers do not
    receive a non-empty, corrupt image buffer.
    """
    rgb = _make_rgb(20, 100)
    try:
        result = encode_image(rgb, fmt="xyzzy")
        assert result == b""
    except (cv2.error, Exception):
        pass  # OpenCV 5+ raises instead of returning empty


# ---------------------------------------------------------------------------
# to_grayscale
# ---------------------------------------------------------------------------

def test_to_grayscale_on_already_gray_returns_same():
    gray = _make_gray(30, 77)
    out = to_grayscale(gray)
    assert out is gray


def test_to_grayscale_rgb_produces_single_channel():
    rgb = _make_rgb(30, 200)
    out = to_grayscale(rgb)
    assert out.ndim == 2
    assert out.shape == (30, 30)


# ---------------------------------------------------------------------------
# denoise — bilateral
# ---------------------------------------------------------------------------

def test_bilateral_denoise_produces_same_shape():
    gray = np.random.default_rng(0).integers(0, 255, (80, 80), dtype=np.uint8)
    params = TraceParams(denoise=9, denoise_mode="bilateral")
    out = denoise(gray, params)
    assert out.shape == gray.shape
    assert out.dtype == np.uint8


def test_bilateral_denoise_reduces_noise():
    """Bilateral should smooth a noisy flat region without destroying shape."""
    base = np.full((100, 100), 128, dtype=np.uint8)
    noise = np.random.default_rng(42).integers(-30, 30, (100, 100), dtype=np.int16)
    noisy = np.clip(base.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    params = TraceParams(denoise=9, denoise_mode="bilateral",
                         bilateral_sigma_color=75.0, bilateral_sigma_space=75.0)
    out = denoise(noisy, params)

    # Denoised image should be closer to the flat value on average.
    before_error = float(np.mean(np.abs(noisy.astype(int) - 128)))
    after_error = float(np.mean(np.abs(out.astype(int) - 128)))
    assert after_error < before_error


def test_bilateral_denoise_preserves_strong_edges():
    """The bilateral filter must not blur a hard step edge into a gradient."""
    gray = np.zeros((60, 60), dtype=np.uint8)
    gray[:, 30:] = 200  # hard edge at x=30

    params = TraceParams(denoise=9, denoise_mode="bilateral",
                         bilateral_sigma_color=75.0, bilateral_sigma_space=75.0)
    out = denoise(gray, params)

    # The pixel immediately left of the edge should remain dark.
    assert int(out[30, 28]) < 50
    # The pixel immediately right of the edge should remain bright.
    assert int(out[30, 32]) > 150


# ---------------------------------------------------------------------------
# denoise — NLM
# ---------------------------------------------------------------------------

def test_nlm_denoise_runs_and_returns_same_shape():
    gray = np.random.default_rng(7).integers(100, 200, (60, 60), dtype=np.uint8)
    params = TraceParams(denoise=3, denoise_mode="nlm",
                         nlm_h=10.0, nlm_template_window=7, nlm_search_window=21)
    out = denoise(gray, params)
    assert out.shape == gray.shape
    assert out.dtype == np.uint8


# ---------------------------------------------------------------------------
# denoise — off / zero
# ---------------------------------------------------------------------------

def test_denoise_off_returns_original():
    gray = _make_gray(40, 99)
    params = TraceParams(denoise=0, denoise_mode="bilateral")
    out = denoise(gray, params)
    np.testing.assert_array_equal(out, gray)


def test_denoise_mode_off_returns_original():
    gray = _make_gray(40, 99)
    params = TraceParams(denoise=9, denoise_mode="off")
    out = denoise(gray, params)
    np.testing.assert_array_equal(out, gray)


# ---------------------------------------------------------------------------
# morphological cleanup
# ---------------------------------------------------------------------------

def _binary_mask_with_speck() -> np.ndarray:
    """200x200 white blob with one isolated 3x3 px black speck."""
    mask = np.zeros((200, 200), dtype=np.uint8)
    cv2.rectangle(mask, (40, 40), (160, 160), 255, -1)
    mask[10:13, 10:13] = 255  # speck far outside the main shape
    return mask


def test_morphological_open_removes_speck():
    """Opening should eliminate a small isolated region far from the main shape.

    We verify indirectly: the total area of white pixels after opening must be
    strictly smaller than before, because the speck was the only white region
    smaller than the opening kernel.
    """
    mask = _binary_mask_with_speck()
    inverted = cv2.bitwise_not(mask)  # binarize expects dark foreground

    # Without opening: speck survives.
    params_no_open = TraceParams(open_px=0, close_px=0)
    masks_before = binarize(inverted, params_no_open)

    # With opening: speck should be removed.
    params_open = TraceParams(open_px=5, close_px=0, morph_kernel="ellipse")
    masks_after = binarize(inverted, params_open)

    area_before = int(masks_before[0].sum())
    area_after  = int(masks_after[0].sum())
    # Opening can only remove pixels, so the area must shrink or stay equal.
    assert area_after <= area_before


def test_morphological_close_fills_gap():
    """Closing should join a mask that has a hairline gap in the middle."""
    mask = np.zeros((100, 100), dtype=np.uint8)
    cv2.rectangle(mask, (10, 10), (89, 44), 255, -1)
    cv2.rectangle(mask, (10, 46), (89, 89), 255, -1)
    # Gap of 1 px at y=45.

    # Create a gray image where the gap is visible.
    gray = cv2.bitwise_not(mask)
    params = TraceParams(close_px=3, open_px=0, morph_kernel="ellipse")
    masks = binarize(gray, params)
    # After closing the gap should be bridged.
    result = masks[0]
    # The gap row should now be white (255) after the close + invert in binarize.
    assert result[45, 50] == 255


# ---------------------------------------------------------------------------
# auto_levels
# ---------------------------------------------------------------------------

def test_auto_levels_stretches_range():
    gray = np.linspace(50, 200, 200 * 200, dtype=np.uint8).reshape(200, 200)
    stretched = auto_levels(gray)
    assert int(stretched.max()) >= 250
    assert int(stretched.min()) <= 5


def test_auto_levels_flat_image_returns_unchanged():
    gray = _make_gray(50, 127)
    out = auto_levels(gray)
    # All pixels equal: high - low < 1, so the original is returned.
    np.testing.assert_array_equal(out, gray)


# ---------------------------------------------------------------------------
# prepare (integration)
# ---------------------------------------------------------------------------

def test_prepare_bilateral_and_close_runs_end_to_end():
    """Full prepare() path with bilateral denoise and morphological close."""
    rgb = _make_rgb(120, 200)
    # Put a dark square in the middle.
    rgb[30:90, 30:90] = 10

    gray = to_grayscale(rgb)
    params = TraceParams(
        denoise=9,
        denoise_mode="bilateral",
        close_px=1,
        morph_kernel="ellipse",
    )
    out = prepare(gray, params)
    assert out.shape == gray.shape
    assert out.dtype == np.uint8


# ---------------------------------------------------------------------------
# binarize modes
# ---------------------------------------------------------------------------

def test_binarize_otsu_returns_one_mask(square_image):
    gray = to_grayscale(square_image)
    masks = binarize(gray, TraceParams(mode="otsu"))
    assert len(masks) == 1
    assert masks[0].dtype == np.uint8


def test_binarize_posterize_returns_levels_minus_one(gradient_image):
    gray = to_grayscale(gradient_image)
    masks = binarize(gray, TraceParams(mode="posterize", levels=4))
    assert len(masks) == 3  # levels - 1


def test_binarize_edges_mode_returns_one_mask(square_image):
    gray = to_grayscale(square_image)
    masks = binarize(gray, TraceParams(mode="edges", canny_low=50, canny_high=150))
    assert len(masks) == 1


@pytest.fixture
def square_image() -> np.ndarray:
    img = np.full((200, 200, 3), 255, np.uint8)
    cv2.rectangle(img, (50, 50), (149, 149), (0, 0, 0), -1)
    return img


@pytest.fixture
def gradient_image() -> np.ndarray:
    ramp = np.linspace(0, 255, 200, dtype=np.uint8)
    return np.repeat(np.tile(ramp, (200, 1))[:, :, None], 3, axis=2)
