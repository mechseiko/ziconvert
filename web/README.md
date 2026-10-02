# zicengine Web UI

A localhost web interface for the zicengine image-to-DXF conversion engine.
Upload PNG/JPEG files and download laser-ready DXF files without installing
the desktop app.

## Architecture

```
browser (port 5173)
    └── Vite dev-server proxy /api/* → FastAPI (port 8000)
            └── imports core/img2dxf (the shared Python engine)
```

The Python engine is never rewritten in JavaScript. The frontend is a thin
HTTP wrapper; the backend is a thin FastAPI wrapper. All conversion logic lives
in `core/`.

---

## Quick Start (Windows)

```bat
web\run.bat
```

Then open **http://localhost:5173** in your browser.

## Quick Start (Linux / macOS)

```bash
bash web/run.sh
```

---

## Manual Start

### Backend (FastAPI)

```bash
# From the repo root, with core/ importable:
cd web/backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

The interactive API docs are available at http://localhost:8000/docs.

### Frontend (Vite + React)

```bash
cd web/frontend
npm install
npm run dev
```

---

## API Reference

### `GET /health`

Returns `{"status": "ok"}`.

### `GET /presets`

Returns the list of built-in presets.

```json
{"presets": ["Logo / clipart", "Photo", "Line art / scan", "Edge outline"]}
```

### `POST /convert`

Convert an image to DXF. Accepts `multipart/form-data`:

| Field         | Type    | Default          | Description                               |
|---------------|---------|------------------|-------------------------------------------|
| `file`        | File    | required         | PNG, JPEG, WebP or BMP image              |
| `width_mm`    | float   | `100.0`          | Target output width in millimetres        |
| `preset`      | string  | `Logo / clipart` | Starting parameter set                    |
| `denoise`     | bool    | `true`           | Bilateral denoise before thresholding     |
| `morphology`  | bool    | `true`           | Morphological close+open on the mask      |
| `shape_fit`   | bool    | `true`           | Snap near-primitive contours to ideal shapes |
| `vector_snap` | bool    | `true`           | Snap near-H/V lines and right angles      |
| `dxf_version` | string  | `R2010`          | DXF version: `R2010`, `R2000`, or `R12`  |

Returns the DXF as an `application/octet-stream` attachment. Response headers
include `X-Path-Count`, `X-Vertex-Count`, `X-Arc-Count`, `X-Width-Mm`,
`X-Height-Mm`, and `X-Summary`.

**curl example:**

```bash
curl -X POST http://localhost:8000/convert \
  -F "file=@logo.png" \
  -F "width_mm=80" \
  -F "preset=Logo / clipart" \
  -F "denoise=true" \
  -F "morphology=true" \
  -F "shape_fit=true" \
  -F "vector_snap=true" \
  -F "dxf_version=R2010" \
  --output output.dxf
```

---

## Frontend Structure

```
web/frontend/src/
├── main.tsx              — React + TanStack Query entry point
├── App.tsx               — Root layout (header, hero, two-column grid)
├── index.css             — Global CSS / design tokens / glassmorphism
├── api/
│   └── convert.ts        — useMutation hook → POST /api/convert
└── components/
    ├── FileUpload.tsx     — Drag-and-drop upload with preview
    ├── SettingsPanel.tsx  — Preset, width, DXF version, toggle switches
    └── ResultPreview.tsx  — Loading state, stats, download button, errors
```

---

## Notes

- The Vite dev-server proxies `/api/*` to `http://localhost:8000` — no CORS
  issues during development.
- For production deployment, build with `npm run build` and serve the `dist/`
  directory behind a reverse proxy (nginx, Caddy) that also forwards
  `/api/*` to the backend.
- The backend has no database, no authentication, and no persistent state.
  It is a pure function: image bytes in, DXF bytes out.
