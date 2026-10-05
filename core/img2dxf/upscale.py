"""Super-resolution: a better upscale, applied before thresholding.

Thresholding quantises every outline to the pixel grid, and that — not the
simplification tolerance — is what limits how clean a traced edge can be.
The engine has always attacked this by tracing an upscaled image, resized
with plain cubic interpolation. Interpolation smooths the staircase; it does
not recover edges the source pixels never recorded. A super-resolution model
tries to, which is why it is offered — and why it is opt-in: a network
inventing detail that was never in the file is a different kind of judgement
than resizing, and one the operator should choose to make.

The contract every backend keeps:

- The output is ``factor`` times the input in each axis (a model's native
  scale is finished off with a cubic resize when it does not divide evenly).
- A backend that cannot run — model missing, package not installed — falls
  back to classical resizing rather than failing the job, and the caller is
  told which backend actually produced the pixels. A summary line that says
  ``sr=dnn`` only ever means dnn ran.
- Nothing is ever downloaded. Models are used from the configured path or
  from ``~/.img2dxf/models/`` when they already sit there; finding nothing,
  ``auto`` degrades to cubic and says so.
"""

from __future__ import annotations

import re
from pathlib import Path

import cv2
import numpy as np

from .params import TraceParams

#: Where a user may drop model files so ``auto``/``dnn``/``esrgan`` find them
#: without configuring a path. The engine reads this directory and never
#: writes to it — the no-surprises answer to "where do I put the model?".
MODEL_DIR = Path.home() / ".img2dxf" / "models"

#: FSRCNN and ESPCN are small and fast; EDSR and LapSRN are heavier but
#: sharper. All four load through the same OpenCV interface, so the filename
#: alone decides which is used.
_MODEL_STEM = re.compile(
    r"(?i)^(?P<family>fsrcnn|espcn|lapsrn|edsr)_x(?P<scale>[234])"
)

#: Real-ESRGAN ncnn models carry the scale in their name almost always
#: (``RealESRGAN_x4plus``, ``realesr-general-x4v3``); the fallback is 4,
#: which is what the family ships.
_ESRGAN_SCALE = re.compile(r"(?i)x(?P<scale>\d)")


def upscale(
    image: np.ndarray, factor: int, params: TraceParams
) -> tuple[np.ndarray, str]:
    """Return ``(upscaled_image, backend_used)``.

    ``factor`` is the supersampling factor from :func:`resolve_detail`; a
    factor of 1 means no upscaling is wanted and the image returns unchanged.
    The second value names the backend that actually produced the pixels —
    ``"off"`` when no upscaling was requested, otherwise the winner of the
    configured backend or whatever it fell back to.
    """
    if factor <= 1:
        return image, "off"

    backend = params.sr_backend

    if backend == "off":
        # The classical supersample the engine has always used.
        return _resize(image, factor, cv2.INTER_CUBIC), "off"
    if backend == "cubic":
        return _resize(image, factor, cv2.INTER_CUBIC), "cubic"
    if backend == "lanczos":
        return _resize(image, factor, cv2.INTER_LANCZOS4), "lanczos"

    for candidate in _neural_candidates(backend):
        result = _run_neural(candidate, image, factor, params.sr_model)
        if result is not None:
            return result, candidate.kind

    # The asked-for backend could not run. Degrade to the sharpest classical
    # resize and say so: an honest summary line is worth more than a silent
    # substitution, but a failed conversion serves nobody.
    return _resize(image, factor, cv2.INTER_LANCZOS4), "lanczos"


def _neural_candidates(backend: str):
    """The neural backends a request may legally resolve to, best first.

    An explicit choice tries exactly that backend; ``auto`` tries everything
    installed. ``auto`` never downloads, so on a clean machine it lands on
    the classical fallback immediately — which is the point: the same
    parameters work everywhere and speed up when a model is provided.
    """
    if backend == "esrgan":
        return [_ESRGAN_MODEL]
    if backend == "dnn":
        return [_DNN_MODEL]
    return [_ESRGAN_MODEL, _DNN_MODEL]


class _DNN_MODEL:
    """OpenCV ``dnn_superres``: FSRCNN, ESPCN, LapSRN or EDSR ``.pb`` files."""

    kind = "dnn"

    @staticmethod
    def resolve(factor: int, model_path: str | None):
        """Pick the ``.pb`` whose scale sits closest to ``factor``.

        An explicit path wins when it parses; otherwise the model directory
        is searched. Running an x2 model to reach a x4 target is fine — the
        remainder is finished with a resize — so distance, not equality,
        orders the candidates.
        """
        paths: list[Path] = []
        if model_path:
            paths.append(Path(model_path))
        elif MODEL_DIR.is_dir():
            paths.extend(sorted(MODEL_DIR.glob("*.pb")))

        parsed = []
        for path in paths:
            match = _MODEL_STEM.match(path.stem)
            if match:
                parsed.append(
                    (abs(int(match["scale"]) - factor), path)
                )
        if not parsed:
            return None
        parsed.sort(key=lambda item: item[0])
        path = parsed[0][1]
        match = _MODEL_STEM.match(path.stem)
        assert match is not None  # parsed above from the same stems
        return match["family"].lower(), int(match["scale"]), path

    @staticmethod
    def run(model, image: np.ndarray) -> np.ndarray | None:
        family, scale, path = model
        try:
            sr = cv2.dnn_superres.DnnSuperResImpl_create()
            sr.readModel(str(path))
            sr.setModel(family, scale)
            out = sr.upsample(image)
        except Exception:  # noqa: BLE001 - any model defect must not fail the job
            return None
        return np.ascontiguousarray(out), scale


class _ESRGAN_MODEL:
    """Real-ESRGAN through the optional ``ncnn`` package.

    ``ncnn`` is not a declared dependency: the backend simply reports itself
    unavailable when the package is missing, and ``auto`` moves on. Models
    are the ``.param``/``.bin`` pairs the official Real-ESRGAN ncnn build
    ships; the ``.bin`` must sit beside the ``.param`` under the same stem.
    """

    kind = "esrgan"

    @staticmethod
    def resolve(factor: int, model_path: str | None):
        try:
            import ncnn  # noqa: F401,PLC0415 - availability is the test
        except ImportError:
            return None

        pairs: list[tuple[int, Path, Path]] = []
        if model_path:
            param = Path(model_path)
            pairs.append((_esrgan_scale(param), param, param.with_suffix(".bin")))
        elif MODEL_DIR.is_dir():
            for param in sorted(MODEL_DIR.glob("*.param")):
                pairs.append((_esrgan_scale(param), param, param.with_suffix(".bin")))
        pairs = [p for p in pairs if p[2].exists()]
        if not pairs:
            return None
        pairs.sort(key=lambda item: abs(item[0] - factor))
        return pairs[0]

    @staticmethod
    def run(model, image: np.ndarray) -> np.ndarray | None:
        try:
            import ncnn  # noqa: PLC0415

            scale, param, model_bin = model
            net = ncnn.Net()
            net.opt.use_vulkan_compute = False
            if net.load_param(str(param)) != 0:
                return None
            if net.load_model(str(model_bin)) != 0:
                return None

            height, width = image.shape[:2]
            mat_in = ncnn.Mat.from_pixels(
                image, ncnn.Mat.PixelType.PIXEL_RGB, width, height
            )
            extractor = net.create_extractor()
            extractor.input("data", mat_in)
            _, mat_out = extractor.extract("output")

            out = np.array(mat_out)
            if out.ndim == 3 and out.shape[0] == 3:
                out = out.transpose(1, 2, 0)
            out = np.clip(out, 0.0, 1.0)
            out = (out * 255.0).round().astype(np.uint8)
            return np.ascontiguousarray(out), scale
        except Exception:  # noqa: BLE001 - inference is strictly optional
            return None


def _esrgan_scale(path: Path) -> int:
    match = _ESRGAN_SCALE.search(path.stem)
    return int(match["scale"]) if match else 4


def _run_neural(
    backend, image: np.ndarray, factor: int, model_path: str | None
) -> tuple[np.ndarray, str] | None:
    """Resolve and run one neural backend, or ``None`` to try the next."""
    model = backend.resolve(factor, model_path)
    if model is None:
        return None
    run = backend.run(model, image)
    if run is None:
        return None
    out, native_scale = run
    if native_scale <= 0:
        return None
    return _to_factor(out, factor, native_scale), backend.kind


def _to_factor(image: np.ndarray, factor: int, done: int) -> np.ndarray:
    """Finish a model's native scale up (or trim it down) to ``factor``."""
    if done == factor:
        return image
    height, width = image.shape[:2]
    return cv2.resize(
        image,
        (round(width * factor / done), round(height * factor / done)),
        interpolation=cv2.INTER_CUBIC,
    )


def _resize(image: np.ndarray, factor: int, interpolation: int) -> np.ndarray:
    height, width = image.shape[:2]
    return cv2.resize(
        image, (width * factor, height * factor), interpolation=interpolation
    )
