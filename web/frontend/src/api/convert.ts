/**
 * API module: POST /api/convert
 *
 * Sends a FormData request to the zicengine FastAPI backend and returns a
 * Blob URL the browser can use to trigger a DXF download.
 */

import { useMutation } from '@tanstack/react-query'

export interface ConvertSettings {
  width_mm: number
  preset: string
  denoise: boolean
  morphology: boolean
  shape_fit: boolean
  vector_snap: boolean
  dxf_version: string
}

export interface ConvertResult {
  blobUrl: string
  filename: string
  summary: string
  meta: {
    pathCount: number
    vertexCount: number
    arcCount: number
    widthMm: number
    heightMm: number
  }
}

interface ConvertInput {
  file: File
  settings: ConvertSettings
}

/**
 * Call POST /api/convert and turn the response body into a Blob URL.
 * The /api prefix is proxied by Vite to http://localhost:8000.
 */
async function convertImage({ file, settings }: ConvertInput): Promise<ConvertResult> {
  const form = new FormData()
  form.append('file', file)
  form.append('width_mm', String(settings.width_mm))
  form.append('preset', settings.preset)
  form.append('denoise', String(settings.denoise))
  form.append('morphology', String(settings.morphology))
  form.append('shape_fit', String(settings.shape_fit))
  form.append('vector_snap', String(settings.vector_snap))
  form.append('dxf_version', settings.dxf_version)

  const response = await fetch('/api/convert', {
    method: 'POST',
    body: form,
  })

  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(
      typeof body.detail === 'string'
        ? body.detail
        : JSON.stringify(body.detail) || 'Conversion failed',
    )
  }

  const blob = await response.blob()
  const blobUrl = URL.createObjectURL(blob)

  const cd = response.headers.get('Content-Disposition') ?? ''
  const match = cd.match(/filename="?([^"]+)"?/)
  const filename = match ? match[1] : `output_${Date.now()}.dxf`

  return {
    blobUrl,
    filename,
    summary: response.headers.get('X-Summary') ?? '',
    meta: {
      pathCount:   Number(response.headers.get('X-Path-Count')   ?? 0),
      vertexCount: Number(response.headers.get('X-Vertex-Count') ?? 0),
      arcCount:    Number(response.headers.get('X-Arc-Count')    ?? 0),
      widthMm:     Number(response.headers.get('X-Width-Mm')     ?? 0),
      heightMm:    Number(response.headers.get('X-Height-Mm')    ?? 0),
    },
  }
}

export function useConvertImage() {
  return useMutation({
    mutationFn: convertImage,
    // Clean up any previously created Blob URL to avoid memory leaks.
    onSuccess: (_data, _vars, _ctx) => {},
    onMutate: () => {},
  })
}

/** Fetch the list of available presets from the backend. */
export async function fetchPresets(): Promise<string[]> {
  const response = await fetch('/api/presets')
  if (!response.ok) return []
  const body = await response.json()
  return body.presets ?? []
}
