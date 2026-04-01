import { useState, useEffect, useRef } from 'react'
import { getMetrics } from '../api/client'
import { AreaChart, Area } from 'recharts'

const MAX_HISTORY = 20

function shortenContainerName(name) {
  const short = name.replace(/^mission-control-/, '').replace(/-1$/, '')
  const aliases = {
    'openclaw-openclaw-gateway': 'claw-gw',
    'openclaw-openclaw-cli': 'claw-cli',
  }
  return aliases[short] || short
}

function formatBytes(bytes) {
  const gb = bytes / 1024 / 1024 / 1024
  return `${gb.toFixed(1)} GB`
}

function Sparkline({ data, dataKey }) {
  return (
    <AreaChart width={80} height={40} data={data}>
      <defs>
        <linearGradient id={`grad-${dataKey}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#00ff41" stopOpacity={0.2} />
          <stop offset="100%" stopColor="#00ff41" stopOpacity={0} />
        </linearGradient>
      </defs>
      <Area
        type="monotone"
        dataKey={dataKey}
        stroke="#00ff41"
        strokeWidth={1.5}
        fill={`url(#grad-${dataKey})`}
        isAnimationActive={false}
      />
    </AreaChart>
  )
}

function MetricsBar() {
  const [metrics, setMetrics] = useState(null)
  const historyRef = useRef({ cpu: [], memory: [], disk: [] })
  const [history, setHistory] = useState({ cpu: [], memory: [], disk: [] })

  useEffect(() => {
    const fetchMetrics = async () => {
      try {
        const data = await getMetrics()
        setMetrics(data)

        const h = historyRef.current
        h.cpu = [...h.cpu, { v: data.cpu.usage_percent }].slice(-MAX_HISTORY)
        h.memory = [...h.memory, { v: data.memory.usage_percent }].slice(-MAX_HISTORY)
        h.disk = [...h.disk, { v: data.disk.usage_percent }].slice(-MAX_HISTORY)
        historyRef.current = h
        setHistory({ ...h })
      } catch {
        // keep last known metrics
      }
    }

    fetchMetrics()
    const interval = setInterval(fetchMetrics, 3000)
    return () => clearInterval(interval)
  }, [])

  if (!metrics) {
    return (
      <div className="border-b border-[#0d2b0d] px-6 h-12 flex items-center">
        <span className="text-xs text-[#3d6b3d]">Loading metrics...</span>
      </div>
    )
  }

  return (
    <div className="border-b border-[#0d2b0d] px-6 h-14 flex items-center">
      <div className="max-w-[1400px] mx-auto w-full flex items-center divide-x divide-[#0d2b0d]">
        {/* CPU */}
        <div className="flex items-center gap-3 pr-6">
          <div>
            <p className="text-[10px] font-medium text-[#3d6b3d] uppercase tracking-wider">CPU</p>
            <p className="text-sm font-medium text-[#c8e6c8] tabular-nums">
              {metrics.cpu.usage_percent.toFixed(1)}%
              <span className="text-[#2a4a2a] text-xs font-normal ml-1">{metrics.cpu.count} cores</span>
            </p>
          </div>
          <Sparkline data={history.cpu} dataKey="v" />
        </div>

        {/* Memory */}
        <div className="flex items-center gap-3 px-6">
          <div>
            <p className="text-[10px] font-medium text-[#3d6b3d] uppercase tracking-wider">Memory</p>
            <p className="text-sm font-medium text-[#c8e6c8] tabular-nums">
              {formatBytes(metrics.memory.used_bytes)}
              <span className="text-[#2a4a2a] text-xs font-normal ml-1">/ {formatBytes(metrics.memory.total_bytes)}</span>
            </p>
          </div>
          <Sparkline data={history.memory} dataKey="v" />
        </div>

        {/* Disk */}
        <div className="flex items-center gap-3 px-6">
          <div>
            <p className="text-[10px] font-medium text-[#3d6b3d] uppercase tracking-wider">Disk</p>
            <p className="text-sm font-medium text-[#c8e6c8] tabular-nums">
              {formatBytes(metrics.disk.used_bytes)}
              <span className="text-[#2a4a2a] text-xs font-normal ml-1">/ {formatBytes(metrics.disk.total_bytes)}</span>
            </p>
          </div>
          <Sparkline data={history.disk} dataKey="v" />
        </div>

        {/* Containers */}
        <div className="flex items-center gap-3 pl-6 min-w-0">
          <div className="min-w-0">
            <p className="text-[10px] font-medium text-[#3d6b3d] uppercase tracking-wider">Containers</p>
            <div className="flex items-center gap-1 overflow-x-auto">
              {[...metrics.docker.containers]
                .filter((c) => c.name.startsWith('mission-control-') || c.name.startsWith('openclaw-'))
                .sort((a, b) => (a.status === 'running' ? 0 : 1) - (b.status === 'running' ? 0 : 1))
                .map((c) => {
                  const running = c.status === 'running'
                  return (
                    <span
                      key={c.name}
                      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] bg-[#00ff41]/[0.04] border border-[#0d2b0d] whitespace-nowrap"
                    >
                      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${running ? 'bg-[#00ff41]' : 'bg-red-400'}`} />
                      <span className={running ? 'text-[#3d6b3d]' : 'text-[#2a4a2a]'}>
                        {shortenContainerName(c.name)}
                      </span>
                    </span>
                  )
                })}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default MetricsBar
