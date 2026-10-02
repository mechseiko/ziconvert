"""Image loading and everything that happens before contours exist.

The output of this module is always a list of ``uint8`` masks where 255 means
"burn this" and 0 means "leave it". Multi-mask output only happens in
posterize mode, where each mask is one tone level.
"""

from __future__ import annotations

from pathlib import Path as FsPath

import cv2
import numpy as np
from PIL import Image

from .params import DEFAULT_DENOISE, TraceParams

#: ``cv2`` shape constants, looked up by the name used in :class:`TraceParams`.
_KERNEL_SHAPES = {
    "ellipse": cv2.MORPH_ELLIPSE,
    "rect": cv2.MORPH_RECT,
    "cross": cv2.MORPH_CROSS,
}


def load_image(path: str | FsPath) -> tuple[np.ndarray, float | None]:
    """Load an image as RGB and return it with its embedded DPI if any.

    Pillow is used rather than ``cv2.imread`` because it reads the DPI metadata
    and copes with non-ASCII paths on Windows, which ``imread`` silently fails
    on by returning ``None``.
    """
    with Image.open(path) as img:
        dpi_info = img.info.get("dpi")
        rgb = np.asarray(img.convert("RGB"))

    dpi: float | None = None
    if dpi_info:
        try:
            value = float(dpi_info[0])
            # Some encoders write 0 or 1; neither is a real resolution.
            if value > 1.0:
                dpi = value
        except (TypeError, ValueError, IndexError):
            dpi = None

    return rgb, dpi


def decode_image(data: bytes) -> np.ndarray:
    """Turn encoded PNG/JPEG bytes into an RGB array.

    The in-memory counterpart of :func:`load_image`, for callers that were
    handed bytes over HTTP rather than a path on disk. OpenCV's decoder is
    used because it is the one that has to read the array back anyway.

    Raises :class:`ValueError` rather than returning ``None``: an undecodable
    upload is a caller mistake worth reporting, and ``cv2.imdecode`` signals it
    by returning nothing at all, which every caller would otherwise have to
    remember to check.
    """
    buffer = np.frombuffer(data, dtype=np.uint8)
    if buffer.size == 0:
        raise ValueError("no image data to decode")
    decoded = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if decoded is None:
        raise ValueError("not a readable PNG, JPEG, BMP, TIFF or WebP image")
    # imdecode yields BGR; everything downstream assumes RGB.
    return cv2.cvtColor(decoded, cv2.COLOR_BGR2RGB)


def encode_image(rgb: np.ndarray, fmt: str = "png") -> bytes:
    """Encode an RGB array back to image bytes, for returning a preview.

    ``fmt`` is the extension without a dot. Returns an empty result rather
    than raising when the encoder does not know the format, so a caller asking
    for an exotic preview simply gets nothing back instead of a failed
    conversion whose DXF was already written.
    """
    suffix = (fmt or "png").lower().lstrip(".")
    ok, encoded = cv2.imencode(f".{suffix}", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    return encoded.tobytes() if ok else b""


def to_grayscale(rgb: np.ndarray) -> np.ndarray:
    if rgb.ndim == 2:
        return rgb
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)


def prepare(gray: np.ndarray, params: TraceParams) -> np.ndarray:
    """Get the grayscale image ready for thresholding.

    Order matters. Tone is fixed first, so the threshold has a full range to
    work with. Denoise comes next, removing specks and flattening mottled
    areas outright rather than letting the later steps smear them into grey
    blobs that survive thresholding. Sharpen then blur come last, because they
    are the two that undo each other.
    """
    out = gray

    if params.auto_levels:
        out = auto_levels(out)
    if params.brightness or params.contrast != 1.0:
        out = cv2.convertScaleAbs(
            out, alpha=params.contrast,
            # Rotate contrast about mid-grey rather than about black, or
            # raising it would also brighten the whole image.
            beta=params.brightness + 128.0 * (1.0 - params.contrast),
        )
    if params.gamma != 1.0:
        out = cv2.LUT(out, _gamma_table(params.gamma))
    if params.denoise_enabled:
        out = denoise(out, params)
    if params.sharpen:
        out = _unsharp(out, params.sharpen)
    if params.blur:
        k = _odd(params.blur)
        out = cv2.GaussianBlur(out, (k, k), 0)

    return out


def denoise(gray: np.ndarray, params: TraceParams) -> np.ndarray:
    """Remove noise with the filter :attr:`TraceParams.denoise_mode` names.

    ``denoise`` is a single strength dial that each mode reads in its own
    units, because the units are not interchangeable: a median of 9 deletes
    whole letters, a bilateral of 3 does nothing at all. Keeping one dial means
    a UI slider and a saved settings file stay meaningful when the mode is
    changed underneath them, with :data:`~img2dxf.params.DEFAULT_DENOISE` as
    the calibration point each mode is tuned around.
    """
    mode = params.denoise_mode
    if mode == "off" or params.denoise <= 0:
        return gray

    if mode == "bilateral":
        # Smooths flat areas while refusing to average across an edge, which
        # is what turns a jagged oval into a curve rather than into a blob.
        return cv2.bilateralFilter(
            gray,
            _odd(params.denoise),
            params.bilateral_sigma_color,
            params.bilateral_sigma_space,
        )

    if mode == "nlm":
        # Compares whole patches instead of single pixels. Strongest and
        # slowest; the strength is scaled off the mode's calibration point.
        reference = DEFAULT_DENOISE.get("nlm", 3) or 1
        return cv2.fastNlMeansDenoising(
            gray,
            None,
            params.nlm_h * params.denoise / reference,
            _odd(params.nlm_template_window),
            _odd(params.nlm_search_window),
        )

    # median, and the fallback for any mode name that got past normalization.
    return cv2.medianBlur(gray, _odd(params.denoise))


def auto_levels(gray: np.ndarray, ignore: float = 0.5) -> np.ndarray:
    """Stretch the tonal range to fill 0-255.

    The black and white points come from percentiles, not from the extremes:
    a single dust speck or blown highlight would otherwise define the range
    and leave the actual artwork as unstretched as before.
    """
    low, high = np.percentile(gray, (ignore, 100.0 - ignore))
    if high - low < 1:
        return gray
    stretched = (gray.astype(np.float32) - low) * (255.0 / (high - low))
    return np.clip(stretched, 0, 255).astype(np.uint8)


def _gamma_table(gamma: float) -> np.ndarray:
    """A 256-entry LUT; this runs on every slider drag, so per-pixel pow is out."""
    values = np.arange(256, dtype=np.float32) / 255.0
    return np.clip(np.power(values, 1.0 / gamma) * 255.0, 0, 255).astype(np.uint8)


def _unsharp(gray: np.ndarray, strength: float) -> np.ndarray:
    """Unsharp mask: push the image away from its own blurred version."""
    blurred = cv2.GaussianBlur(gray, (0, 0), 2.0)
    return cv2.addWeighted(gray, 1.0 + strength, blurred, -strength, 0)


def binarize(gray: np.ndarray, params: TraceParams) -> list[np.ndarray]:
    """Produce one or more burn masks from a prepared grayscale image.

    Dark pixels become foreground by default, which matches how people read a
    black-on-white logo; ``params.invert`` swaps that.
    """
    mode = params.mode

    if mode == "posterize":
        masks = _posterize(gray, params.levels)
    elif mode == "edges":
        masks = [_edges(gray, params)]
    elif mode == "adaptive":
        masks = [
            cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY_INV, params.adaptive_block, params.adaptive_c,
            )
        ]
    elif mode == "fixed":
        _, mask = cv2.threshold(gray, params.threshold, 255, cv2.THRESH_BINARY_INV)
        masks = [mask]
    else:  # otsu
        _, mask = cv2.threshold(
            gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
        )
        masks = [mask]

    # Edge masks are already outlines; inverting them would trace the
    # background instead, which is never what the control means.
    if params.invert and mode != "edges":
        masks = [cv2.bitwise_not(m) for m in masks]

    return [_morphology(m, params) for m in masks]


def _posterize(gray: np.ndarray, levels: int) -> list[np.ndarray]:
    """Quantize into ``levels`` tones and return a cumulative mask per tone.

    Masks are cumulative (each darker level includes everything darker still)
    so the tones nest like contour lines on a map rather than meeting at
    hairline seams that the laser would leave as visible gaps.
    """
    edges = np.linspace(0, 255, levels + 1)
    masks = []
    # Skip the lightest band: that is the paper, not a burn.
    for i in range(levels - 1):
        cutoff = edges[i + 1]
        masks.append((gray <= cutoff).astype(np.uint8) * 255)
    return masks


def _edges(gray: np.ndarray, params: TraceParams) -> np.ndarray:
    low, high = sorted((params.canny_low, params.canny_high))
    mask = cv2.Canny(gray, low, max(high, low + 1))
    if params.edge_dilate:
        mask = cv2.dilate(mask, _kernel(params.edge_dilate))
    return mask


def _morphology(mask: np.ndarray, params: TraceParams) -> np.ndarray:
    """Close hairline gaps, then remove specks.

    Closing runs first: doing it the other way round would delete thin
    features that closing was about to repair.

    Both honour :attr:`~img2dxf.params.TraceParams.morph_kernel` and
    ``morph_iterations``. Several light passes usually beat one heavy one —
    repeated small discs follow an outline around, while a single large disc
    stamps over it and rounds off corners that were meant to be sharp.
    """
    iterations = max(1, int(params.morph_iterations))
    if params.close_px:
        mask = cv2.morphologyEx(
            mask, cv2.MORPH_CLOSE,
            _kernel(params.close_px, params.morph_kernel),
            iterations=iterations,
        )
    if params.open_px:
        mask = cv2.morphologyEx(
            mask, cv2.MORPH_OPEN,
            _kernel(params.open_px, params.morph_kernel),
            iterations=iterations,
        )
    return mask


def _kernel(radius: int, shape: str = "ellipse") -> np.ndarray:
    """A structuring element of the given radius.

    The shape defaults to an ellipse rather than the rectangle OpenCV would
    give you, because a circle closed with a square kernel comes out with
    flats on it — the most visible way to get morphology wrong.
    """
    size = _odd(radius)
    return cv2.getStructuringElement(
        _KERNEL_SHAPES.get(shape, cv2.MORPH_ELLIPSE), (size, size)
    )


def _odd(radius: int) -> int:
    size = max(1, int(radius))
    return size if size % 2 == 1 else size + 1
