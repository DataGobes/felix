import { useState, useEffect } from 'react'
import { getMetrics } from '../api/client'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { Badge } from '@/components/ui/badge'

function formatBytes(bytes) {
  const gb = bytes / 1024 / 1024 / 1024
  return `${gb.toFixed(1)} GB`
}

function formatUptime(seconds) {
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  return `${days}d ${hours}h`
}

const fakeData = {
  cpu: { usage_percent: 34, count: 4 },
  memory: { used_bytes: 4564246528, total_bytes: 16722137088, usage_percent: 27.3 },
  disk: { used_bytes: 25258037248, total_bytes: 65445814272, usage_percent: 38.6 },
  uptime_seconds: 164094,
  network: { bytes_sent: 182, bytes_recv: 848 },
  docker: {
    running: 5, total: 7,
    containers: [
      { name: 'felix-gateway', status: 'running', image: 'felix:local' },
      { name: 'rag-search', status: 'running', image: 'rag-rag-search:latest' },
      { name: 'rag-postgres', status: 'running', image: 'pgvector/pgvector:pg16' },
      { name: 'rag-ingestion', status: 'running', image: 'rag-rag-ingestion:latest' },
      { name: 'felix-cli', status: 'exited', image: 'felix:local' },
    ]
  }
}

function ServerMonitor() {
  const [metrics, setMetrics] = useState(fakeData)

  useEffect(() => {
    const fetchMetrics = async () => {
      try {
        const data = await getMetrics()
        setMetrics(data)
      } catch (error) {
        setMetrics(fakeData)
      }
    }

    fetchMetrics()
    const interval = setInterval(fetchMetrics, 3000)
    return () => clearInterval(interval)
  }, [])

  return (
    <Card className="bg-[#0a0f0a] border-[#0d2b0d] col-span-2">
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-[#c8e6c8]">🖥️ Server Monitor</CardTitle>
        <span className="text-xs text-[#3d6b3d]">Uptime: {formatUptime(metrics.uptime_seconds)}</span>
      </CardHeader>
      <CardContent className="space-y-6">

        {/* CPU & Memory & Disk */}
        <div className="grid grid-cols-3 gap-4">
          <div className="space-y-1">
            <div className="flex justify-between text-sm text-[#5a8a5a]">
              <span>CPU ({metrics.cpu.count} cores)</span>
              <span>{metrics.cpu.usage_percent}%</span>
            </div>
            <Progress value={metrics.cpu.usage_percent} className="h-2" />
          </div>
          <div className="space-y-1">
            <div className="flex justify-between text-sm text-[#5a8a5a]">
              <span>Memory</span>
              <span>{formatBytes(metrics.memory.used_bytes)} / {formatBytes(metrics.memory.total_bytes)}</span>
            </div>
            <Progress value={metrics.memory.usage_percent} className="h-2" />
          </div>
          <div className="space-y-1">
            <div className="flex justify-between text-sm text-[#5a8a5a]">
              <span>Disk</span>
              <span>{formatBytes(metrics.disk.used_bytes)} / {formatBytes(metrics.disk.total_bytes)}</span>
            </div>
            <Progress value={metrics.disk.usage_percent} className="h-2" />
          </div>
        </div>

        {/* Docker Containers */}
        <div>
          <div className="flex items-center gap-2 mb-2">
            <span className="text-sm text-[#5a8a5a]">🐳 Docker</span>
            <Badge variant="outline" className="text-[#00ff41] border-[#00ff41]/30 text-xs">
              {metrics.docker.running} / {metrics.docker.total} running
            </Badge>
          </div>
          <div className="grid grid-cols-2 gap-2">
            {metrics.docker.containers.map(container => (
              <div key={container.name} className="flex items-center justify-between px-3 py-2 rounded bg-[#0a120a]">
                <span className="text-xs text-[#8ab88a] truncate">{container.name}</span>
                <Badge
                  variant="outline"
                  className={container.status === 'running'
                    ? 'text-emerald-400 border-emerald-800 text-xs ml-2 shrink-0'
                    : 'text-red-400 border-red-800 text-xs ml-2 shrink-0'}
                >
                  {container.status}
                </Badge>
              </div>
            ))}
          </div>
        </div>

      </CardContent>
    </Card>
  )
}

export default ServerMonitor