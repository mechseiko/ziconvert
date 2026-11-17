import { useCallback, useEffect, useRef, useState } from 'react'
import { FileImage, Upload, X } from 'lucide-react'

interface FileUploadProps {
  file: File | null
  onFileSelect: (file: File) => void
  onClear: () => void
  disabled?: boolean
}

const ACCEPTED = 'image/png,image/jpeg,image/webp,image/bmp'
const ACCEPTED_EXT = ['.png', '.jpg', '.jpeg', '.webp', '.bmp']

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`
}

export default function FileUpload({
  file,
  onFileSelect,
  onClear,
  disabled = false,
}: FileUploadProps) {
  const [isDragOver, setIsDragOver] = useState(false)
  const [preview, setPreview] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    return () => {
      if (preview) URL.revokeObjectURL(preview)
    }
  }, [preview])

  const accept = useCallback(
    (f: File) => {
      if (!f.type.startsWith('image/')) return
      onFileSelect(f)
      setPreview((old) => {
        if (old) URL.revokeObjectURL(old)
        return URL.createObjectURL(f)
      })
    },
    [onFileSelect],
  )

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setIsDragOver(false)
      if (disabled) return
      const f = e.dataTransfer.files[0]
      if (f) accept(f)
    },
    [accept, disabled],
  )

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (f) accept(f)
  }

  const handleClear = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (inputRef.current) inputRef.current.value = ''
    setPreview((old) => {
      if (old) URL.revokeObjectURL(old)
      return null
    })
    onClear()
  }

  return (
    <div
      className={`upload-panel ${isDragOver ? 'drag-over' : ''} ${
        disabled ? 'opacity-50 pointer-events-none' : ''
      }`}
      onClick={() => inputRef.current?.click()}
      onDragOver={(e) => {
        e.preventDefault()
        if (!disabled) setIsDragOver(true)
      }}
      onDragLeave={() => setIsDragOver(false)}
      onDrop={handleDrop}
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-label="Upload image file"
      aria-disabled={disabled}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          inputRef.current?.click()
        }
      }}
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
        <div className="upload-selected">
          <div className="relative justify-self-center">
            <div className="preview-frame">
              <img src={preview} alt="Selected image preview" />
            </div>
            <button
              type="button"
              className="remove-file"
              onClick={handleClear}
              aria-label="Remove file"
              disabled={disabled}
            >
              <X size={13} />
            </button>
          </div>

          <div className="file-meta">
            <div className="file-name">
              <FileImage size={16} />
              <span>{file.name}</span>
            </div>
            <div className="file-details">
              <span>
                Size <strong>{formatSize(file.size)}</strong>
              </span>
              <span>
                Type <strong>{file.type || 'image'}</strong>
              </span>
            </div>
            <p className="replace-note">Click or drop another image to replace it.</p>
          </div>
        </div>
      ) : (
        <div className="upload-empty">
          <div className="upload-icon">
            <Upload size={22} />
          </div>
          <p className="upload-title">Drop an image here</p>
          <p className="upload-subtitle">or choose a file from your device</p>
          <div className="format-row">
            {ACCEPTED_EXT.map((ext) => (
              <span key={ext} className="format">
                {ext}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
