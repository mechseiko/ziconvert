import { useState, useCallback } from 'react'
import FileUpload from '@/components/FileUpload'
import ResultPreview from '@/components/ResultPreview'
import { useConvertImage } from '@/api/convert'
import { Cpu, Github, Zap } from 'lucide-react'

const LASERCUT_SETTINGS: ConvertSettings = {
  width_mm: 100,
  preset: 'Logo / clipart',
  denoise: true,
  morphology: true,
  shape_fit: true,
  vector_snap: true,
  dxf_version: 'R2010',
}

export default function App() {
  const [file, setFile] = useState<File | null>(null)

  const { mutate, data, isPending, isError, error, isSuccess, reset } =
    useConvertImage()

  const handleFileSelect = useCallback(
    (f: File) => {
      setFile(f)
      reset()
    },
    [reset],
  )

  const handleConvert = () => {
    if (!file) return
    mutate({ file, settings: LASERCUT_SETTINGS })
  }

  return (
    <div className="min-h-screen flex flex-col">
      {/* ── Header ────────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-50 border-b border-white/5 backdrop-blur-xl bg-surface-950/60">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-brand-600 flex items-center justify-center shadow-lg shadow-brand-600/30">
              <Cpu size={16} className="text-white" />
            </div>
            <div>
              <span className="font-bold text-white tracking-tight">ziconvert</span>
              <span className="ml-2 text-xs text-brand-400 font-mono bg-brand-950 border border-brand-800 px-1.5 py-0.5 rounded">
                v0.1
              </span>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <span className="hidden sm:flex items-center gap-1.5 text-xs text-slate-400">
              <Zap size={12} className="text-brand-400" />
              Image → DXF converter
            </span>
            <a
              href="https://github.com/mechseiko/ziconvert"
              target="_blank"
              rel="noreferrer"
              className="btn-secondary !px-3 !py-2"
              aria-label="View source on GitHub"
            >
              <Github size={15} />
              <span className="hidden sm:inline">Source</span>
            </a>
          </div>
        </div>
      </header>

      {/* ── Hero ──────────────────────────────────────────────────────── */}
      <section className="max-w-6xl mx-auto px-4 sm:px-6 pt-12 pb-8 text-center">
        <div className="inline-flex items-center gap-2 badge badge-loading mb-5">
          <span className="w-1.5 h-1.5 rounded-full bg-brand-400 animate-pulse-slow" />
          Running locally — no upload to cloud
        </div>
        <h1 className="text-4xl sm:text-5xl font-extrabold tracking-tight mb-4">
          <span className="gradient-text text-glow">Image to DXF</span>
          <br className="hidden sm:block" />
          <span className="text-white"> Converter</span>
        </h1>
        <p className="text-slate-400 text-lg max-w-xl mx-auto leading-relaxed">
          Upload a PNG or JPEG image and convert it to a DXF file suitable for
          CAD and laser cutting applications. Processing is done locally on your machine.
        </p>
      </section>

      {/* ── Main content ──────────────────────────────────────────────── */}
      <main className="flex-1 max-w-6xl mx-auto w-full px-4 sm:px-6 pb-16">
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-6">
          {/* Left column */}
          <div className="flex flex-col gap-6">
            <FileUpload
              file={file}
              onFileSelect={handleFileSelect}
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
          </div>

          {/* Right column — convert button */}
          <div className="flex flex-col gap-4">
            <button
              className="btn-primary w-full py-4 text-base glow-brand"
              onClick={handleConvert}
              disabled={!file || isPending}
            >
              {isPending ? (
                <>
                  <svg className="animate-spin-slow w-5 h-5" viewBox="0 0 24 24" fill="none">
                    <circle
                      className="opacity-25"
                      cx="12" cy="12" r="10"
                      stroke="currentColor" strokeWidth="4"
                    />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z"
                    />
                  </svg>
                  Converting…
                </>
              ) : (
                <>
                  <Zap size={18} />
                  Convert to DXF
                </>
              )}
            </button>

            {/* Engine info card */}
            <div className="glass p-4 text-xs text-slate-500 space-y-1.5 animate-fade-in">
              <div className="flex justify-between">
                <span>Engine</span>
                <span className="text-slate-400 font-mono">ziconvert core</span>
              </div>
              <div className="flex justify-between">
                <span>Backend</span>
                <span className="text-slate-400 font-mono">FastAPI / localhost:8000</span>
              </div>
              <div className="flex justify-between">
                <span>Output</span>
                <span className="text-slate-400 font-mono">DXF (LWPOLYLINE + arcs)</span>
              </div>
            </div>
          </div>
        </div>
      </main>

      {/* ── Footer ────────────────────────────────────────────────────── */}
      <footer className="border-t border-white/5 py-6 text-center text-xs text-slate-600">
        ziconvert ·{' '}
        <a
          href="https://github.com/mechseiko/ziconvert"
          className="text-slate-500 hover:text-slate-300 transition-colors"
          target="_blank"
          rel="noreferrer"
        >
          mechseiko/ziconvert
        </a>{' '}
        · MIT licence
      </footer>
    </div>
  )
}
