import { useCallback, useRef, useState } from 'react'
import { Upload, X, FileImage } from 'lucide-react'

interface FileUploadProps {
  file: File | null
  onFileSelect: (file: File) => void
  disabled?: boolean
}

const ACCEPTED = 'image/png,image/jpeg,image/webp,image/bmp'
const ACCEPTED_EXT = ['.png', '.jpg', '.jpeg', '.webp', '.bmp']

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`
}

export default function FileUpload({ file, onFileSelect, disabled = false }: FileUploadProps) {
  const [isDragOver, setIsDragOver] = useState(false)
  const [preview, setPreview] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const accept = (f: File) => {
    if (!f.type.startsWith('image/')) return
    onFileSelect(f)
    const url = URL.createObjectURL(f)
    setPreview(url)
  }

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setIsDragOver(false)
      if (disabled) return
      const f = e.dataTransfer.files[0]
      if (f) accept(f)
    },
    [disabled],
  )

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (f) accept(f)
  }

  const handleClear = (e: React.MouseEvent) => {
    e.stopPropagation()
    setPreview(null)
    if (inputRef.current) inputRef.current.value = ''
    // Signal parent by re-mounting — handled via file=null from parent reset()
  }

  return (
    <div
      className={`drop-zone p-6 cursor-pointer transition-all duration-200 ${
        isDragOver ? 'drag-over' : ''
      } ${disabled ? 'opacity-50 pointer-events-none' : ''}`}
      onClick={() => inputRef.current?.click()}
      onDragOver={(e) => { e.preventDefault(); setIsDragOver(true) }}
      onDragLeave={() => setIsDragOver(false)}
      onDrop={handleDrop}
      role="button"
      tabIndex={0}
      aria-label="Upload image file"
      onKeyDown={(e) => e.key === 'Enter' && inputRef.current?.click()}
    >
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED}
        className="hidden"
        onChange={handleInputChange}
        id="file-input"
      />

      {file && preview ? (
        /* ── File preview state ─────────────────────────────────────── */
        <div className="flex gap-5 items-start animate-slide-up">
          <div className="relative flex-shrink-0">
            <img
              src={preview}
              alt="Preview"
              className="w-28 h-28 object-cover rounded-xl border border-white/10 shadow-lg"
            />
            <button
              className="absolute -top-2 -right-2 w-6 h-6 rounded-full bg-red-500/80 hover:bg-red-400 flex items-center justify-center transition-colors shadow"
              onClick={handleClear}
              aria-label="Remove file"
              disabled={disabled}
            >
              <X size={12} className="text-white" />
            </button>
          </div>

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <FileImage size={14} className="text-brand-400 flex-shrink-0" />
              <span className="text-sm font-medium text-white truncate">{file.name}</span>
            </div>
            <div className="text-xs text-slate-500 space-y-1">
              <div>{formatSize(file.size)}</div>
              <div className="text-slate-600">Click or drag to replace</div>
            </div>
          </div>
        </div>
      ) : (
        /* ── Empty state ─────────────────────────────────────────────── */
        <div className="flex flex-col items-center justify-center py-10 text-center animate-fade-in">
          <div className="w-16 h-16 rounded-2xl bg-brand-950 border border-brand-800/50 flex items-center justify-center mb-4 group-hover:scale-105 transition-transform">
            <Upload size={28} className="text-brand-400" />
          </div>
          <p className="text-white font-semibold mb-1">Drop your image here</p>
          <p className="text-sm text-slate-500 mb-3">or click to browse files</p>
          <div className="flex gap-2 flex-wrap justify-center">
            {ACCEPTED_EXT.map((ext) => (
              <span
                key={ext}
                className="text-xs px-2 py-0.5 rounded bg-surface-700 border border-white/5 text-slate-400 font-mono"
              >
                {ext}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
