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
      className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-[#00ff41]/30 focus:ring-offset-2 focus:ring-offset-[#0a0f0a] disabled:cursor-not-allowed disabled:opacity-50 ${
        enabled
          ? 'border-[#00ff41]/60 bg-[#00ff41]/20'
          : 'border-[#1a3a1a] bg-[#0d1f0d]'
      }`}
    >
      <span
        className={`pointer-events-none inline-block h-5 w-5 rounded-full shadow-lg transition-transform duration-200 ${
          enabled
            ? 'translate-x-5 bg-[#00ff41] shadow-[0_0_8px_#00ff41]'
            : 'translate-x-0 bg-[#3d6b3d]'
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
    <div className="bg-[#0a0f0a] rounded-xl border border-[#0d2b0d]">
      <div className="px-6 py-5">
        <div className="flex items-center gap-2.5 mb-1.5">
          <h3 className="text-sm font-medium text-[#5a8a5a]">{item.label}</h3>
          {saved && (
            <span className="text-[10px] text-emerald-400 bg-emerald-500/10 px-1.5 py-0.5 rounded animate-pulse">
              saved
            </span>
          )}
          {saving && (
            <div className="w-3 h-3 border border-[#00ff41]/40 border-t-[#00ff41] rounded-full animate-spin" />
          )}
        </div>
        <p className="text-xs text-[#2a4a2a] leading-relaxed mb-3">{item.description}</p>
        <input
          ref={inputRef}
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onBlur={handleBlur}
          onKeyDown={handleKeyDown}
          disabled={saving}
          className="w-full bg-[#0d1f0d] border border-[#1a3a1a] rounded-lg px-3 py-2 text-xs text-[#c8e6c8] font-mono placeholder-[#1e3a1e] focus:outline-none focus:border-[#00ff41]/40 focus:ring-1 focus:ring-[#00ff41]/20 transition-colors disabled:opacity-50"
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
        <div className="bg-[#0a0f0a] rounded-xl shadow-lg shadow-black/20 p-8">
          <div className="flex items-center gap-3">
            <div className="w-4 h-4 border-2 border-[#00ff41]/40 border-t-[#00ff41] rounded-full animate-spin" />
            <span className="text-sm text-[#3d6b3d]">Loading pipeline configuration...</span>
          </div>
        </div>
      </div>
    )
  }

  if (error && !config) {
    return (
      <div className="max-w-3xl mx-auto">
        <div className="bg-[#0a0f0a] rounded-xl shadow-lg shadow-black/20 p-8">
          <p className="text-sm text-red-400">{error}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-3xl mx-auto">
      <div className="mb-6">
        <h1 className="text-lg font-bold text-[#00ff41] tracking-wider uppercase">Pipeline Settings</h1>
        <p className="text-xs text-[#3d6b3d] mt-1">Configure document enrichment features for the ingestion pipeline</p>
      </div>

      {error && (
        <div className="mb-4 px-4 py-2.5 rounded-lg bg-red-500/10 border border-red-500/20 text-xs text-red-400">
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
              className={`bg-[#0a0f0a] rounded-xl border transition-all duration-300 ${
                enabled
                  ? 'border-[#00ff41]/30 shadow-[0_0_15px_-5px_#00ff4130]'
                  : 'border-[#0d2b0d]'
              }`}
            >
              <div className="px-6 py-5 flex items-start justify-between gap-6">
                <div className="min-w-0">
                  <div className="flex items-center gap-2.5">
                    <h3 className={`text-sm font-medium transition-colors ${
                      enabled ? 'text-[#c8e6c8]' : 'text-[#5a8a5a]'
                    }`}>
                      {item.label}
                    </h3>
                    {justSaved && (
                      <span className="text-[10px] text-emerald-400 bg-emerald-500/10 px-1.5 py-0.5 rounded animate-pulse">
                        saved
                      </span>
                    )}
                    {isSaving && (
                      <div className="w-3 h-3 border border-[#00ff41]/40 border-t-[#00ff41] rounded-full animate-spin" />
                    )}
                  </div>
                  <p className={`text-xs mt-1.5 leading-relaxed transition-colors ${
                    enabled ? 'text-[#3d6b3d]' : 'text-[#2a4a2a]'
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
          <h2 className="text-xs font-medium text-[#5a8a5a] uppercase tracking-wider mb-3">Configuration</h2>
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

      <div className="mt-6 px-4 py-3 rounded-lg bg-[#00ff41]/[0.03] border border-[#0d2b0d]">
        <p className="text-[11px] text-[#3d6b3d] leading-relaxed">
          <span className="text-[#00ff41] font-medium">Note:</span> Changes take effect on the next ingestion run.
          Documents already processed will not be re-enriched automatically.
        </p>
      </div>
    </div>
  )
}

export default ControlPanel
