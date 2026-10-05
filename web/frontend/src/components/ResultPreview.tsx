import { useEffect } from 'react'
import {
  CheckCircle,
  XCircle,
  Download,
  FileCode2,
  AlertCircle,
  Layers,
  BarChart3,
} from 'lucide-react'

interface Meta {
  pathCount: number
  vertexCount: number
  arcCount: number
  widthMm: number
  heightMm: number
  srUsed?: string
}

interface ResultPreviewProps {
  isLoading: boolean
  isSuccess: boolean
  isError: boolean
  error: Error | null
  blobUrl: string | null
  filename: string | null
  summary: string | null
  meta: Meta | null
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex flex-col items-center p-3 rounded-xl bg-surface-800 border border-white/5">
      <span className="text-lg font-bold font-mono text-white">{value}</span>
      <span className="text-xs text-slate-500 mt-0.5">{label}</span>
    </div>
  )
}

export default function ResultPreview({
  isLoading,
  isSuccess,
  isError,
  error,
  blobUrl,
  filename,
  summary,
  meta,
}: ResultPreviewProps) {
  // Revoke the blob URL when the component unmounts or a new one is generated.
  useEffect(() => {
    return () => {
      if (blobUrl) URL.revokeObjectURL(blobUrl)
    }
  }, [blobUrl])

  if (!isLoading && !isSuccess && !isError) {
    return null
  }

  return (
    <div className="glass p-6 animate-slide-up">
      {/* ── Loading ─────────────────────────────────────────────────── */}
      {isLoading && (
        <div className="flex flex-col items-center py-8 gap-4">
          <div className="relative">
            <div className="w-16 h-16 rounded-full border-2 border-brand-800 border-t-brand-400 animate-spin-slow" />
            <div className="absolute inset-0 flex items-center justify-center">
              <FileCode2 size={20} className="text-brand-400" />
            </div>
          </div>
          <div className="text-center">
            <p className="text-white font-medium">Converting…</p>
            <p className="text-sm text-slate-500 mt-1">Running the tracing engine</p>
          </div>
          <div className="w-full max-w-xs h-1 bg-surface-700 rounded-full overflow-hidden">
            <div className="h-full bg-brand-500 rounded-full shimmer" style={{ width: '60%' }} />
          </div>
        </div>
      )}

      {/* ── Success ──────────────────────────────────────────────────── */}
      {isSuccess && blobUrl && (
        <div className="animate-fade-in">
          {/* Status badge */}
          <div className="flex items-center gap-2 mb-5">
            <CheckCircle size={18} className="text-emerald-400" />
            <span className="font-semibold text-white">Conversion complete</span>
            <span className="badge badge-success ml-auto">DXF ready</span>
          </div>

          {/* Stats grid */}
          {meta && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-5">
              <Stat label="Paths" value={meta.pathCount} />
              <Stat label="Vertices" value={meta.vertexCount.toLocaleString()} />
              <Stat label="Arcs" value={meta.arcCount} />
              <Stat
                label="Size"
                value={`${meta.widthMm.toFixed(0)}×${meta.heightMm.toFixed(0)} mm`}
              />
            </div>
          )}

          {/* Summary text */}
          {summary && (
            <div className="flex items-start gap-2 p-3 rounded-lg bg-surface-700 border border-white/5 mb-5">
              <BarChart3 size={14} className="text-slate-400 mt-0.5 flex-shrink-0" />
              <p className="text-xs font-mono text-slate-400 break-all">{summary}</p>
            </div>
          )}

          {/* Super-resolution report — only when something actually ran */}
          {meta?.srUsed && meta.srUsed !== 'off' && (
            <p className="text-xs text-slate-500 mb-5">
              Upscaled with <span className="font-mono text-slate-400">{meta.srUsed}</span>
              {meta.srUsed === 'lanczos' && ' (neural model unavailable — degraded resize)'}
            </p>
          )}

          {/* Download button */}
          <a
            href={blobUrl}
            download={filename ?? 'output.dxf'}
            className="btn-primary w-full !py-3 glow-brand"
          >
            <Download size={16} />
            Download {filename ?? 'output.dxf'}
          </a>

          <p className="text-xs text-slate-600 text-center mt-3">
            <Layers size={11} className="inline mr-1" />
            Open in LightBurn, RDWorks, AutoCAD or Inkscape
          </p>
        </div>
      )}

      {/* ── Error ───────────────────────────────────────────────────── */}
      {isError && error && (
        <div className="animate-fade-in">
          <div className="flex items-center gap-2 mb-4">
            <XCircle size={18} className="text-red-400" />
            <span className="font-semibold text-white">Conversion failed</span>
            <span className="badge badge-error ml-auto">Error</span>
          </div>

          <div className="p-4 rounded-xl bg-red-950/30 border border-red-800/40">
            <div className="flex items-start gap-2">
              <AlertCircle size={14} className="text-red-400 mt-0.5 flex-shrink-0" />
              <p className="text-sm text-red-300 break-words">{error.message}</p>
            </div>
          </div>

          <p className="text-xs text-slate-500 mt-3">
            Try adjusting the threshold mode, minimum area, or check that the
            backend is running on <code className="font-mono text-slate-400">localhost:8000</code>.
          </p>
        </div>
      )}
    </div>
  )
}
