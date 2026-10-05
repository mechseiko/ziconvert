import { useEffect, useState } from 'react'
import { Settings2, Sliders } from 'lucide-react'
import type { ConvertSettings } from '@/api/convert'
import { fetchPresets } from '@/api/convert'

interface SettingsPanelProps {
  settings: ConvertSettings
  onChange: (s: ConvertSettings) => void
  disabled?: boolean
}

const DXF_VERSIONS = ['R2010', 'R2000', 'R12'] as const
const SR_BACKENDS = ['off', 'auto', 'cubic', 'lanczos', 'dnn', 'esrgan'] as const

interface SnapTolerance {
  key: 'snap_axis_deg' | 'snap_merge_mm' | 'snap_right_angle_deg' | 'snap_circle_mm'
  label: string
  hint: string
  step: number
}

const SNAP_TOLERANCES: SnapTolerance[] = [
  {
    key: 'snap_axis_deg',
    label: 'Axis snap',
    hint: 'Degrees off H/V that still snaps exact',
    step: 0.05,
  },
  {
    key: 'snap_merge_mm',
    label: 'Coordinate merge',
    hint: 'mm — near-equal coordinates collapse onto one',
    step: 0.01,
  },
  {
    key: 'snap_right_angle_deg',
    label: 'Right angles',
    hint: 'Degrees off 90° that still squares up',
    step: 0.1,
  },
  {
    key: 'snap_circle_mm',
    label: 'Circle claim',
    hint: 'mm — rings this close export as true CIRCLEs',
    step: 0.05,
  },
]

function Toggle({
  id,
  checked,
  onChange,
  disabled,
}: {
  id: string
  checked: boolean
  onChange: (v: boolean) => void
  disabled?: boolean
}) {
  return (
    <label className={`toggle ${disabled ? 'opacity-50' : 'cursor-pointer'}`} htmlFor={id}>
      <input
        id={id}
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        disabled={disabled}
      />
      <span className="slider" />
    </label>
  )
}

function Row({
  label,
  hint,
  children,
}: {
  label: string
  hint?: string
  children: React.ReactNode
}) {
  return (
    <div className="flex items-center justify-between gap-3 py-2.5 border-b border-white/5 last:border-0">
      <div className="min-w-0">
        <p className="text-sm text-slate-200 font-medium">{label}</p>
        {hint && <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">{hint}</p>}
      </div>
      <div className="flex-shrink-0">{children}</div>
    </div>
  )
}

export default function SettingsPanel({ settings, onChange, disabled = false }: SettingsPanelProps) {
  const [presets, setPresets] = useState<string[]>([
    'Logo / clipart', 'Photo', 'Line art / scan', 'Edge outline',
  ])

  useEffect(() => {
    fetchPresets().then((p) => { if (p.length > 0) setPresets(p) }).catch(() => {})
  }, [])

  const set = <K extends keyof ConvertSettings>(key: K, value: ConvertSettings[K]) => {
    onChange({ ...settings, [key]: value })
  }

  return (
    <div className="glass-hi p-5 animate-slide-up">
      {/* Header */}
      <div className="flex items-center gap-2 mb-5">
        <Settings2 size={16} className="text-brand-400" />
        <h2 className="text-sm font-semibold text-white tracking-wide uppercase">Settings</h2>
      </div>

      {/* Preset */}
      <div className="mb-5">
        <label htmlFor="preset" className="block text-xs font-medium text-slate-400 mb-1.5 uppercase tracking-wider">
          Preset
        </label>
        <select
          id="preset"
          value={settings.preset}
          onChange={(e) => set('preset', e.target.value)}
          disabled={disabled}
          className="w-full bg-surface-800 border border-white/8 rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-brand-500 transition-colors"
        >
          {presets.map((p) => (
            <option key={p} value={p}>{p}</option>
          ))}
        </select>
      </div>

      {/* Width slider */}
      <div className="mb-5">
        <div className="flex items-center justify-between mb-2">
          <label htmlFor="width-slider" className="text-xs font-medium text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
            <Sliders size={11} />
            Output width
          </label>
          <span className="text-sm font-mono text-brand-300">{settings.width_mm} mm</span>
        </div>
        <input
          id="width-slider"
          type="range"
          min={10}
          max={1000}
          step={5}
          value={settings.width_mm}
          onChange={(e) => set('width_mm', Number(e.target.value))}
          disabled={disabled}
          className="w-full"
        />
        <div className="flex justify-between text-xs text-slate-600 mt-1">
          <span>10 mm</span>
          <span>1000 mm</span>
        </div>
      </div>

      {/* DXF version */}
      <div className="mb-5">
        <label htmlFor="dxf-version" className="block text-xs font-medium text-slate-400 mb-1.5 uppercase tracking-wider">
          DXF Version
        </label>
        <select
          id="dxf-version"
          value={settings.dxf_version}
          onChange={(e) => set('dxf_version', e.target.value)}
          disabled={disabled}
          className="w-full bg-surface-800 border border-white/8 rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-brand-500 transition-colors"
        >
          {DXF_VERSIONS.map((v) => (
            <option key={v} value={v}>{v}</option>
          ))}
        </select>
      </div>

      {/* Enhancement toggles */}
      <div className="space-y-0">
        <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">Enhancements</p>

        <Row
          label="Bilateral Denoise"
          hint="Smooths flat areas while preserving edges"
        >
          <Toggle
            id="toggle-denoise"
            checked={settings.denoise}
            onChange={(v) => set('denoise', v)}
            disabled={disabled}
          />
        </Row>

        <Row
          label="Morphological Cleanup"
          hint="Fills hairline gaps, removes specks"
        >
          <Toggle
            id="toggle-morphology"
            checked={settings.morphology}
            onChange={(v) => set('morphology', v)}
            disabled={disabled}
          />
        </Row>

        <Row
          label="Primitive Snapping"
          hint="Snaps circles, ellipses & rectangles to ideal shapes"
        >
          <Toggle
            id="toggle-shape-fit"
            checked={settings.shape_fit}
            onChange={(v) => set('shape_fit', v)}
            disabled={disabled}
          />
        </Row>

        <Row
          label="Straighten"
          hint="Flattens wavy runs that are structurally straight"
        >
          <Toggle
            id="toggle-straighten"
            checked={settings.straighten}
            onChange={(v) => set('straighten', v)}
            disabled={disabled}
          />
        </Row>

        <Row
          label="Vector Snap"
          hint="Snaps near-H/V lines and right-angle corners"
        >
          <Toggle
            id="toggle-vector-snap"
            checked={settings.vector_snap}
            onChange={(v) => set('vector_snap', v)}
            disabled={disabled}
          />
        </Row>
      </div>

      {/* Super-resolution */}
      <div className="mt-5">
        <label htmlFor="sr-backend" className="block text-xs font-medium text-slate-400 mb-1.5 uppercase tracking-wider">
          Super-resolution
        </label>
        <select
          id="sr-backend"
          value={settings.sr_backend}
          onChange={(e) => set('sr_backend', e.target.value)}
          disabled={disabled}
          className="w-full bg-surface-800 border border-white/8 rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-brand-500 transition-colors"
        >
          {SR_BACKENDS.map((b) => (
            <option key={b} value={b}>{b}</option>
          ))}
        </select>
        <p className="text-xs text-slate-500 mt-1.5 leading-relaxed">
          Upscale before tracing. Neural models (dnn, esrgan) need model files
          installed locally; without them the run degrades to lanczos and says so.
        </p>
      </div>

      {/* Advanced snap tolerances */}
      <details className="mt-4 group">
        <summary className="text-xs font-medium text-slate-500 uppercase tracking-wider cursor-pointer select-none hover:text-slate-300 transition-colors">
          Advanced tolerances
        </summary>
        <div className="mt-3 space-y-3">
          {SNAP_TOLERANCES.map(({ key, label, hint, step }) => (
            <div key={key}>
              <label htmlFor={`tol-${key}`} className="block text-xs text-slate-300 font-medium">
                {label}
              </label>
              <input
                id={`tol-${key}`}
                type="number"
                min={0}
                step={step}
                placeholder="preset default"
                value={settings[key] ?? ''}
                onChange={(e) => {
                  const raw = e.target.value
                  set(key, raw === '' ? undefined : Number(raw))
                }}
                disabled={disabled}
                className="w-full bg-surface-800 border border-white/8 rounded-lg px-3 py-2 text-sm text-white font-mono placeholder:text-slate-600 focus:outline-none focus:border-brand-500 transition-colors"
              />
              <p className="text-xs text-slate-500 mt-0.5">{hint}</p>
            </div>
          ))}
        </div>
      </details>
    </div>
  )
}
