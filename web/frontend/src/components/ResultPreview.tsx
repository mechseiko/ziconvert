import { useEffect } from 'react'
import {
  AlertCircle,
  CheckCircle,
  Download,
  FileCode2,
  Layers,
  Scan,
  XCircle,
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
    <div className="stat">
      <span className="stat-value">{value}</span>
      <span className="stat-label">{label}</span>
    </div>
  )
}

function IdleOutput() {
  return (
    <div className="output-empty">
      <div className="specimen" aria-hidden="true">
        <svg viewBox="0 0 240 150" role="img" aria-label="Vector path specimen">
          <path className="grid-line" d="M0 25H240M0 50H240M0 75H240M0 100H240M0 125H240" />
          <path className="grid-line" d="M30 0V150M60 0V150M90 0V150M120 0V150M150 0V150M180 0V150M210 0V150" />
          <path className="vector-line" d="M38 112V54h58v58H38Z" />
          <path className="vector-line" d="M126 96a34 34 0 1 0 68 0 34 34 0 1 0-68 0Z" />
          <path className="vector-detail" d="M126 62h76M126 88h52" />
          <path className="vector-cut" d="M52 96h116M166 54v58" />
        </svg>
      </div>
      <p className="output-title">Your DXF will appear here</p>
      <p className="output-copy">
        The traced paths, vertex count, arc count and finished size are reported after conversion.
      </p>
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
  useEffect(() => {
    return () => {
      if (blobUrl) URL.revokeObjectURL(blobUrl)
    }
  }, [blobUrl])

  return (
    <div className="panel output-panel">
      <div className="panel-head">
        <div className="panel-title">
          <FileCode2 size={16} />
          Output
        </div>
        <span className="panel-meta">DXF result</span>
      </div>

      <div className="output-body">
        {!isLoading && !isSuccess && !isError && <IdleOutput />}

        {isLoading && (
          <div className="output-state">
            <div className="state-head">
              <div className="state-icon loading">
                <Scan size={17} />
              </div>
              <div>
                <div className="state-title">Tracing contours</div>
                <div className="state-subtitle">Running the ziconvert engine</div>
              </div>
            </div>
            <div className="trace-loader" aria-hidden="true">
              <div className="trace-line" />
            </div>
            <div className="progress-track" aria-hidden="true">
              <div className="progress-bar" />
            </div>
          </div>
        )}

        {isSuccess && blobUrl && (
          <div className="output-state">
            <div className="state-head">
              <div className="state-icon success">
                <CheckCircle size={17} />
              </div>
              <div>
                <div className="state-title">Conversion complete</div>
                <div className="state-subtitle">{filename ?? 'output.dxf'}</div>
              </div>
            </div>

            {meta && (
              <div className="stat-grid">
                <Stat label="Paths" value={meta.pathCount} />
                <Stat label="Vertices" value={meta.vertexCount.toLocaleString()} />
                <Stat label="Arcs" value={meta.arcCount} />
                <Stat
                  label="Size"
                  value={`${meta.widthMm.toFixed(0)}×${meta.heightMm.toFixed(0)} mm`}
                />
              </div>
            )}

            {summary && <div className="summary-box">{summary}</div>}

            {meta?.srUsed && meta.srUsed !== 'off' && (
              <p className="output-copy">
                Upscaled with <strong>{meta.srUsed}</strong>
                {meta.srUsed === 'lanczos' && ' (neural model unavailable — degraded resize)'}
              </p>
            )}

            <a href={blobUrl} download={filename ?? 'output.dxf'} className="button button-primary download-button">
              <Download size={16} />
              Download {filename ?? 'output.dxf'}
            </a>
            <p className="output-note">
              <Layers size={12} />
              Open in LightBurn, RDWorks, AutoCAD or Inkscape
            </p>
          </div>
        )}

        {isError && (
          <div className="output-state">
            <div className="state-head">
              <div className="state-icon error">
                <XCircle size={17} />
              </div>
              <div>
                <div className="state-title">Conversion failed</div>
                <div className="state-subtitle">The engine rejected this run</div>
              </div>
            </div>
            <div className="error-box">
              <p>
                <AlertCircle size={13} style={{ display: 'inline', verticalAlign: '-2px', marginRight: 6 }} />
                {error?.message ?? 'Conversion failed'}
              </p>
            </div>
            <p className="output-copy">
              Try another preset, raise the minimum area, or check that the API is reachable.
            </p>
          </div>
        )}
      </div>

      <div className="output-footer">
        <span>ziconvert core</span>
        <span>DXF / millimetres</span>
      </div>
    </div>
  )
}
