import { useState, useCallback } from 'react'
import { Github, Image as ImageIcon } from 'lucide-react'
import FileUpload from '@/components/FileUpload'
import ResultPreview from '@/components/ResultPreview'
import SettingsPanel from '@/components/SettingsPanel'
import { useConvertImage } from '@/api/convert'
import type { ConvertSettings } from '@/api/convert'

const DEFAULT_SETTINGS: ConvertSettings = {
  width_mm: 100,
  preset: 'Logo / clipart',
  denoise: true,
  morphology: true,
  shape_fit: true,
  vector_snap: true,
  straighten: true,
  sr_backend: 'off',
  dxf_version: 'R2010',
}

function LogoMark() {
  return (
    <span className="brand-mark" aria-hidden="true">
      <svg viewBox="0 0 32 32" fill="none">
        <path d="M7 24V8h18" stroke="currentColor" strokeWidth="2" />
        <path d="M7 24h11" stroke="currentColor" strokeWidth="2" />
        <path d="M18 8h7v7" stroke="#ff4d00" strokeWidth="2" />
      </svg>
    </span>
  )
}

function HeroArt() {
  return (
    <div className="hero-art" aria-hidden="true">
      <svg viewBox="0 0 520 330">
        <path className="art-grid" d="M0 42H520M0 84H520M0 126H520M0 168H520M0 210H520M0 252H520M0 294H520" />
        <path className="art-grid" d="M52 0V330M104 0V330M156 0V330M208 0V330M260 0V330M312 0V330M364 0V330M416 0V330M468 0V330" />
        <path className="art-shape draw-path draw-path-1" pathLength="1" d="M58 226V98h126v128H58Z" />
        <path className="art-detail draw-path draw-path-2" pathLength="1" d="M232 214a52 52 0 1 0 104 0 52 52 0 1 0-104 0Z" />
        <path className="art-detail draw-path draw-path-3" pathLength="1" d="M232 138h82M232 168h56" />
        <path className="art-cut draw-path draw-path-4" pathLength="1" d="M78 194h154M286 142v72" />
        <path className="art-cut draw-path draw-path-2" pathLength="1" d="M322 286h96" />
      </svg>
    </div>
  )
}

export default function App() {
  const [file, setFile] = useState<File | null>(null)
  const [settings, setSettings] = useState<ConvertSettings>(DEFAULT_SETTINGS)

  const { mutate, data, isPending, isError, error, isSuccess, reset } =
    useConvertImage()

  const handleFileSelect = useCallback(
    (f: File) => {
      setFile(f)
      reset()
    },
    [reset],
  )

  const handleClearFile = useCallback(() => {
    setFile(null)
    reset()
  }, [reset])

  const handleConvert = () => {
    if (!file) return
    mutate({ file, settings })
  }

  return (
    <div className="shell">
      <header className="topbar">
        <div className="topbar-inner">
          <a className="brand" href="/" aria-label="ziconvert home">
            <LogoMark />
            <span className="brand-name">ziconvert</span>
            <span className="brand-version">v0.2.0</span>
          </a>

          <div className="top-meta">
            <span>PNG / JPEG / WebP / BMP</span>
            <span className="sep" />
            <span>DXF output</span>
          </div>

          <a
            href="https://github.com/mechseiko/ziconvert"
            target="_blank"
            rel="noreferrer"
            className="button button-quiet"
            aria-label="View source on GitHub"
          >
            <Github size={15} />
            <span>Source</span>
          </a>
        </div>
      </header>

      <main>
        <section className="page-width hero">
          <div className="hero-copy">
            <div className="eyebrow">Raster to vector · DXF for laser and CAD</div>
            <h1>Turn images into laser-ready DXF.</h1>
            <p className="lede">
              Drop a raster image, set the finished width, and export clean contours
              for LightBurn, RDWorks, LaserCAD and CAD workflows.
            </p>
            <div className="fact-row">
              <span className="fact">True millimetre scale</span>
              <span className="fact">DXF R2010 / R2000 / R12</span>
              <span className="fact">Arcs and circles preserved</span>
              <span className="fact">No account required</span>
            </div>
            <HeroArt />
          </div>

          <aside className="panel source-panel" aria-label="Source image">
            <div className="panel-head">
              <div className="panel-title">
                <ImageIcon size={16} />
                Source image
              </div>
              <span className="panel-meta">step 1</span>
            </div>
            <FileUpload
              file={file}
              onFileSelect={handleFileSelect}
              onClear={handleClearFile}
              disabled={isPending}
            />
          </aside>
        </section>

        <section className="page-width bench" aria-label="Conversion bench">
          <SettingsPanel
            settings={settings}
            onChange={setSettings}
            onConvert={handleConvert}
            canConvert={Boolean(file)}
            isPending={isPending}
            disabled={isPending}
          />

          <ResultPreview
            isLoading={isPending}
            isSuccess={isSuccess}
            isError={isError}
            error={error}
            blobUrl={data?.blobUrl ?? null}
            filename={data?.filename ?? null}
            summary={data?.summary ?? null}
            meta={data?.meta ?? null}
          />
        </section>
      </main>

      <footer className="footer">
        <div className="footer-inner">
          <span>ziconvert — image to DXF</span>
          <span>
            <a
              href="https://github.com/mechseiko/ziconvert"
              target="_blank"
              rel="noreferrer"
            >
              mechseiko/ziconvert
            </a>{' '}
            · MIT
          </span>
        </div>
      </footer>
    </div>
  )
}
