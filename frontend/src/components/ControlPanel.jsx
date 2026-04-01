import { useState, useEffect, useRef } from 'react'
import { getConfig, updateConfig } from '../api/client'

const isBoolean = (v) => v === 'true' || v === 'false'

function Toggle({ enabled, onToggle, disabled }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={enabled}
      disabled={disabled}
      onClick={onToggle}
      className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-ember/30 focus:ring-offset-2 focus:ring-offset-white disabled:cursor-not-allowed disabled:opacity-50 ${
        enabled
          ? 'border-ember/60 bg-ember/20'
          : 'border-warm-200 bg-warm-bg'
      }`}
    >
      <span
        className={`pointer-events-none inline-block h-5 w-5 rounded-full shadow-lg transition-transform duration-200 ${
          enabled
            ? 'translate-x-5 bg-ember'
            : 'translate-x-0 bg-warm-400'
        }`}
      />
    </button>
  )
}

function TextConfigField({ item, saving, saved, onSave }) {
  const [value, setValue] = useState(item.value)
  const inputRef = useRef(null)

  useEffect(() => { setValue(item.value) }, [item.value])

  const handleBlur = () => {
    if (value !== item.value) onSave(value)
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      inputRef.current?.blur()
    }
  }

  return (
    <div className="bg-white rounded-xl border border-warm-200">
      <div className="px-6 py-5">
        <div className="flex items-center gap-2.5 mb-1.5">
          <h3 className="text-sm font-medium text-warm-600">{item.label}</h3>
          {saved && (
            <span className="text-[10px] text-emerald-600 bg-emerald-50 px-1.5 py-0.5 rounded animate-pulse">
              saved
            </span>
          )}
          {saving && (
            <div className="w-3 h-3 border border-ember/40 border-t-ember rounded-full animate-spin" />
          )}
        </div>
        <p className="text-xs text-warm-400 leading-relaxed mb-3">{item.description}</p>
        <input
          ref={inputRef}
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onBlur={handleBlur}
          onKeyDown={handleKeyDown}
          disabled={saving}
          className="w-full bg-warm-bg border border-warm-200 rounded-lg px-3 py-2 text-xs text-warm-900 font-mono placeholder-warm-400 focus:outline-none focus:border-ember/40 focus:ring-1 focus:ring-ember/20 transition-colors disabled:opacity-50"
          placeholder="https://..."
        />
      </div>
    </div>
  )
}

function ControlPanel() {
  const [config, setConfig] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(null) // key currently being saved
  const [saved, setSaved] = useState(null)   // key that was just saved

  useEffect(() => {
    const fetchConfig = async () => {
      try {
        const data = await getConfig()
        setConfig(data)
      } catch (err) {
        setError('Failed to load pipeline configuration')
      } finally {
        setLoading(false)
      }
    }
    fetchConfig()
  }, [])

  const handleToggle = async (key) => {
    const item = config.find(c => c.key === key)
    if (!item || saving) return

    const newValue = item.value === 'true' ? 'false' : 'true'

    // Optimistic update
    setConfig(prev => prev.map(c => c.key === key ? { ...c, value: newValue } : c))
    setSaving(key)
    setSaved(null)

    try {
      await updateConfig({ [key]: newValue })
      setSaved(key)
      setTimeout(() => setSaved(null), 2000)
    } catch {
      // Revert on failure
      setConfig(prev => prev.map(c => c.key === key ? { ...c, value: item.value } : c))
      setError('Failed to update setting')
      setTimeout(() => setError(null), 3000)
    } finally {
      setSaving(null)
    }
  }

  const handleTextSave = async (key, value) => {
    const item = config.find(c => c.key === key)
    if (!item || saving || item.value === value) return

    setSaving(key)
    setSaved(null)

    try {
      await updateConfig({ [key]: value })
      setConfig(prev => prev.map(c => c.key === key ? { ...c, value } : c))
      setSaved(key)
      setTimeout(() => setSaved(null), 2000)
    } catch {
      setError('Failed to update setting')
      setTimeout(() => setError(null), 3000)
    } finally {
      setSaving(null)
    }
  }

  if (loading) {
    return (
      <div className="max-w-3xl mx-auto">
        <div className="bg-white rounded-xl shadow-sm p-8">
          <div className="flex items-center gap-3">
            <div className="w-4 h-4 border-2 border-ember/40 border-t-ember rounded-full animate-spin" />
            <span className="text-sm text-warm-500">Loading pipeline configuration...</span>
          </div>
        </div>
      </div>
    )
  }

  if (error && !config) {
    return (
      <div className="max-w-3xl mx-auto">
        <div className="bg-white rounded-xl shadow-sm p-8">
          <p className="text-sm text-red-600">{error}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-3xl mx-auto">
      <div className="mb-6">
        <h1 className="text-lg font-semibold text-warm-900">Pipeline Settings</h1>
        <p className="text-xs text-warm-500 mt-1">Configure document enrichment features for the ingestion pipeline</p>
      </div>

      {error && (
        <div className="mb-4 px-4 py-2.5 rounded-lg bg-red-50 border border-red-200 text-xs text-red-600">
          {error}
        </div>
      )}

      <div className="grid gap-4">
        {config.filter(item => isBoolean(item.value)).map(item => {
          const enabled = item.value === 'true'
          const isSaving = saving === item.key
          const justSaved = saved === item.key

          return (
            <div
              key={item.key}
              className={`bg-white rounded-xl border transition-all duration-300 ${
                enabled
                  ? 'border-ember/30'
                  : 'border-warm-200'
              }`}
            >
              <div className="px-6 py-5 flex items-start justify-between gap-6">
                <div className="min-w-0">
                  <div className="flex items-center gap-2.5">
                    <h3 className={`text-sm font-medium transition-colors ${
                      enabled ? 'text-warm-900' : 'text-warm-600'
                    }`}>
                      {item.label}
                    </h3>
                    {justSaved && (
                      <span className="text-[10px] text-emerald-600 bg-emerald-50 px-1.5 py-0.5 rounded animate-pulse">
                        saved
                      </span>
                    )}
                    {isSaving && (
                      <div className="w-3 h-3 border border-ember/40 border-t-ember rounded-full animate-spin" />
                    )}
                  </div>
                  <p className={`text-xs mt-1.5 leading-relaxed transition-colors ${
                    enabled ? 'text-warm-500' : 'text-warm-400'
                  }`}>
                    {item.description}
                  </p>
                </div>
                <div className="pt-0.5">
                  <Toggle
                    enabled={enabled}
                    onToggle={() => handleToggle(item.key)}
                    disabled={!!saving}
                  />
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {config.some(item => !isBoolean(item.value)) && (
        <div className="mt-6">
          <h2 className="text-xs font-medium text-warm-600 uppercase tracking-wider mb-3">Configuration</h2>
          <div className="grid gap-4">
            {config.filter(item => !isBoolean(item.value)).map(item => (
              <TextConfigField
                key={item.key}
                item={item}
                saving={saving === item.key}
                saved={saved === item.key}
                onSave={(value) => handleTextSave(item.key, value)}
              />
            ))}
          </div>
        </div>
      )}

      <div className="mt-6 px-4 py-3 rounded-lg bg-warm-bg border border-warm-200">
        <p className="text-[11px] text-warm-500 leading-relaxed">
          <span className="text-ember font-medium">Note:</span> Changes take effect on the next ingestion run.
          Documents already processed will not be re-enriched automatically.
        </p>
      </div>
    </div>
  )
}

export default ControlPanel
