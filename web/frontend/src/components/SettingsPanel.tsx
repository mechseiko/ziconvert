import { useEffect, useState, type CSSProperties } from 'react'
import { Settings2 } from 'lucide-react'
import type { ConvertSettings } from '@/api/convert'
import { fetchPresets } from '@/api/convert'

interface SettingsPanelProps {
  settings: ConvertSettings
  onChange: (s: ConvertSettings) => void
  onConvert: () => void
  canConvert: boolean
  isPending: boolean
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

function ToggleRow({
  id,
  label,
  hint,
  checked,
  onChange,
  disabled,
}: {
  id: string
  label: string
  hint: string
  checked: boolean
  onChange: (v: boolean) => void
  disabled?: boolean
}) {
  return (
    <div className="toggle-row">
      <div className="toggle-copy">
        <p className="toggle-title">{label}</p>
        <p className="toggle-hint">{hint}</p>
      </div>
      <label className="switch" htmlFor={id}>
        <input
          id={id}
          type="checkbox"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
          disabled={disabled}
        />
        <span />
      </label>
    </div>
  )
}

export default function SettingsPanel({
  settings,
  onChange,
  onConvert,
  canConvert,
  isPending,
  disabled = false,
}: SettingsPanelProps) {
  const [presets, setPresets] = useState<string[]>([
    'Logo / clipart', 'Photo', 'Line art / scan', 'Edge outline',
  ])

  useEffect(() => {
    fetchPresets().then((p) => { if (p.length > 0) setPresets(p) }).catch(() => {})
  }, [])

  const set = <K extends keyof ConvertSettings>(key: K, value: ConvertSettings[K]) => {
    onChange({ ...settings, [key]: value })
  }

  const widthFill = `${((settings.width_mm - 10) / 990) * 100}%`

  return (
    <div className="panel settings-panel">
      <div className="panel-head">
        <div className="panel-title">
          <Settings2 size={16} />
          Job settings
        </div>
        <span className="panel-meta">trace parameters</span>
      </div>

      <div className="settings-body">
        <div className="field">
          <label className="field-label" htmlFor="preset">
            Preset
          </label>
          <div className="select-wrap">
            <select
              id="preset"
              value={settings.preset}
              onChange={(e) => set('preset', e.target.value)}
              disabled={disabled}
              className="select"
            >
              {presets.map((p) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="field range-field">
          <div className="range-top">
            <label className="range-label" htmlFor="width-slider">
              Finished width
            </label>
            <span className="range-value">{settings.width_mm} mm</span>
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
            style={{ '--range-fill': widthFill } as CSSProperties}
          />
          <div className="range-scale">
            <span>10 mm</span>
            <span>1000 mm</span>
          </div>
        </div>

        <div className="field">
          <label className="field-label" htmlFor="dxf-version">
            DXF version
          </label>
          <div className="select-wrap">
            <select
              id="dxf-version"
              value={settings.dxf_version}
              onChange={(e) => set('dxf_version', e.target.value)}
              disabled={disabled}
              className="select"
            >
              {DXF_VERSIONS.map((v) => (
                <option key={v} value={v}>{v}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="section-label">Engine refinements</div>
        <div className="toggle-list">
          <ToggleRow
            id="toggle-denoise"
            label="Bilateral denoise"
            hint="Smooths flat areas while preserving edges"
            checked={settings.denoise}
            onChange={(v) => set('denoise', v)}
            disabled={disabled}
          />
          <ToggleRow
            id="toggle-morphology"
            label="Morphological cleanup"
            hint="Fills hairline gaps and removes specks"
            checked={settings.morphology}
            onChange={(v) => set('morphology', v)}
            disabled={disabled}
          />
          <ToggleRow
            id="toggle-shape-fit"
            label="Primitive snapping"
            hint="Snaps circles, ellipses and rectangles to ideal shapes"
            checked={settings.shape_fit}
            onChange={(v) => set('shape_fit', v)}
            disabled={disabled}
          />
          <ToggleRow
            id="toggle-straighten"
            label="Straighten"
            hint="Flattens wavy runs that are structurally straight"
            checked={settings.straighten}
            onChange={(v) => set('straighten', v)}
            disabled={disabled}
          />
          <ToggleRow
            id="toggle-vector-snap"
            label="Vector snap"
            hint="Snaps near-H/V lines and right-angle corners"
            checked={settings.vector_snap}
            onChange={(v) => set('vector_snap', v)}
            disabled={disabled}
          />
        </div>

        <div className="field" style={{ marginTop: 20 }}>
          <label className="field-label" htmlFor="sr-backend">
            Super-resolution
          </label>
          <div className="select-wrap">
            <select
              id="sr-backend"
              value={settings.sr_backend}
              onChange={(e) => set('sr_backend', e.target.value)}
              disabled={disabled}
              className="select"
            >
              {SR_BACKENDS.map((b) => (
                <option key={b} value={b}>{b}</option>
              ))}
            </select>
          </div>
          <p className="field-hint">
            Upscale before tracing. Neural models need local model files; without them the run degrades to lanczos.
          </p>
        </div>

        <details className="advanced">
          <summary>Advanced tolerances</summary>
          <div className="advanced-grid">
            {SNAP_TOLERANCES.map(({ key, label, hint, step }) => (
              <div key={key}>
                <label className="tolerance-label" htmlFor={`tol-${key}`}>
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
                  className="number-input"
                />
                <p className="tolerance-hint">{hint}</p>
              </div>
            ))}
          </div>
        </details>

        <div className="convert-wrap">
          <button
            type="button"
            className="button button-primary"
            onClick={onConvert}
            disabled={!canConvert || isPending || disabled}
          >
            {isPending ? 'Tracing paths…' : 'Convert to DXF'}
          </button>
          <p className="convert-status">
            {canConvert ? 'Ready to trace the selected image' : 'Choose an image to enable conversion'}
          </p>
        </div>
      </div>
    </div>
  )
}
