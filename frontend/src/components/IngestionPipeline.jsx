import { useIngestionStatus } from '../hooks/useIngestionStatus'

const STAGES = [
  { key: 'queued',          label: 'Queued' },
  { key: 'hashing',         label: 'Hash' },
  { key: 'converting',      label: 'Convert' },
  { key: 'chunking',        label: 'Chunk' },
  { key: 'embedding',       label: 'Embed' },
  { key: 'storing_images',  label: 'Images' },
  { key: 'storing_tables',  label: 'Tables' },
  { key: 'storing_layout',  label: 'Layout' },
  { key: 'completed',       label: 'Done' },
]

const STAGE_INDEX = Object.fromEntries(STAGES.map((s, i) => [s.key, i]))

function getProgressText(status, progress) {
  if (!progress || typeof progress !== 'object') return null

  switch (status) {
    case 'hashing':
      return progress.sha256 ? `SHA: ${progress.sha256.slice(0, 8)}...` : null
    case 'converting': {
      if (!progress.gpu) return null
      const labels = {
        sending_to_gpu: 'Uploading to GPU...',
        gpu_processing: 'GPU processing...',
        receiving_result: 'Downloading result...',
      }
      return labels[progress.stage] || 'GPU conversion'
    }
    case 'chunking':
      return progress.total_chunks ? `${progress.total_chunks} chunks` : null
    case 'embedding': {
      const { embedded, total_chunks } = progress
      if (embedded != null && total_chunks) return `${embedded}/${total_chunks} chunks`
      return null
    }
    case 'storing_images':
      return progress.images_stored != null ? `${progress.images_stored} images` : null
    case 'storing_tables':
      return progress.tables_stored != null ? `${progress.tables_stored} tables` : null
    case 'storing_layout':
      return progress.pages != null ? `${progress.pages} pages` : null
    case 'completed': {
      const parts = []
      if (progress.total_chunks) parts.push(`${progress.total_chunks} chunks`)
      if (progress.images) parts.push(`${progress.images} img`)
      if (progress.tables) parts.push(`${progress.tables} tbl`)
      return parts.length ? parts.join(' · ') : 'Done'
    }
    default:
      return null
  }
}

function StageNode({ stage, status, isFailed, progress }) {
  // Determine node state relative to job's current status
  const jobIdx = STAGE_INDEX[status] ?? -1
  const stageIdx = STAGE_INDEX[stage.key]

  let state = 'future' // dim
  if (isFailed && stage.key === status) state = 'failed'
  else if (isFailed && stageIdx < jobIdx) state = 'completed'
  else if (stageIdx < jobIdx) state = 'completed'
  else if (stageIdx === jobIdx) state = 'active'

  const nodeClasses = {
    completed: 'bg-ember border-ember',
    active:    'bg-ember/20 border-ember',
    failed:    'bg-red-50 border-red-300',
    future:    'bg-warm-bg border-warm-200',
  }

  const labelClasses = {
    completed: 'text-ember',
    active:    'text-ember',
    failed:    'text-red-600',
    future:    'text-warm-400',
  }

  const showGpu = stage.key === 'converting' && state === 'active' && progress?.gpu

  return (
    <div className="flex flex-col items-center gap-1 min-w-0">
      <div className="relative">
        <div className={`w-3 h-3 rounded-full border-2 transition-all duration-500 ${nodeClasses[state]}`} />
        {showGpu && (
          <span className="absolute -top-2.5 -right-3 text-[7px] font-bold text-amber-600 bg-amber-50 px-1 rounded leading-tight">
            GPU
          </span>
        )}
      </div>
      <span className={`text-[9px] font-medium uppercase tracking-wider whitespace-nowrap ${labelClasses[state]}`}>
        {stage.label}
      </span>
    </div>
  )
}

function Connector({ fromStage, status, isFailed }) {
  const jobIdx = STAGE_INDEX[status] ?? -1
  const fromIdx = STAGE_INDEX[fromStage]

  let completed = fromIdx < jobIdx
  let active = fromIdx === jobIdx - 1 && !isFailed

  return (
    <div className="flex-1 flex items-center min-w-[8px] -mt-3">
      <div
        className={`h-0.5 w-full rounded transition-all duration-500 ${
          completed
            ? 'bg-ember/60'
            : active
              ? 'bg-ember/30'
              : 'border-warm-200'
        }`}
      />
    </div>
  )
}

function EmbeddingProgressBar({ progress }) {
  if (!progress?.embedded || !progress?.total_chunks) return null
  const pct = Math.min(100, Math.round((progress.embedded / progress.total_chunks) * 100))

  return (
    <div className="w-full h-1 border-warm-200 rounded-full overflow-hidden mt-1">
      <div
        className="h-full bg-ember rounded-full transition-all duration-700 ease-out"
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}

function JobCard({ job }) {
  const isFailed = job.status === 'failed'
  const isCompleted = job.status === 'completed'
  const progressText = getProgressText(job.status, job.progress)

  // Calculate fade for completed/failed jobs
  let opacity = 1
  if ((isCompleted || isFailed) && job.completed_at) {
    const elapsed = (Date.now() - new Date(job.completed_at).getTime()) / 1000
    if (elapsed > 45) opacity = Math.max(0, 1 - (elapsed - 45) / 15) // fade 45-60s
  }

  return (
    <div
      className="px-4 py-3 rounded-lg border border-warm-200 bg-white transition-opacity duration-1000"
      style={{ opacity }}
    >
      {/* File info */}
      <div className="flex items-center justify-between mb-2.5">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-xs text-warm-900 font-medium truncate">{job.filename}</span>
          <span className="text-[10px] text-warm-400 font-mono flex-shrink-0">{job.index_slug}</span>
        </div>
        {isFailed && (
          <span className="text-[10px] text-red-600 flex-shrink-0">FAILED</span>
        )}
      </div>

      {/* Stage pipeline */}
      <div className="flex items-start gap-0">
        {STAGES.map((stage, i) => (
          <div key={stage.key} className="contents">
            <StageNode stage={stage} status={job.status} isFailed={isFailed} progress={job.progress} />
            {i < STAGES.length - 1 && (
              <Connector fromStage={stage.key} status={job.status} isFailed={isFailed} />
            )}
          </div>
        ))}
      </div>

      {/* Progress detail + embedding bar */}
      <div className="mt-2 min-h-[16px]">
        {job.status === 'embedding' && <EmbeddingProgressBar progress={job.progress} />}
        {progressText && (
          <p className={`text-[10px] mt-1 ${isFailed ? 'text-red-600' : 'text-warm-500'}`}>
            {progressText}
          </p>
        )}
        {isFailed && job.error_message && (
          <p className="text-[10px] text-red-500 mt-0.5 truncate" title={job.error_message}>
            {job.error_message}
          </p>
        )}
      </div>
    </div>
  )
}

export default function IngestionPipeline() {
  const { jobs, connected } = useIngestionStatus()

  // Hide entirely when no jobs
  if (!jobs || jobs.length === 0) return null

  const activeCount = jobs.filter(j => !['completed', 'failed'].includes(j.status)).length

  return (
    <div className="mb-6">
      {/* Header */}
      <div className="flex items-center gap-3 mb-3">
        <h2 className="text-xs font-medium text-warm-500 uppercase tracking-wider">
          Ingestion Pipeline
        </h2>
        {activeCount > 0 && (
          <span className="px-1.5 py-0.5 text-[10px] font-bold rounded bg-ember/[0.08] text-ember tabular-nums">
            {activeCount}
          </span>
        )}
        <div className="flex items-center gap-1.5 ml-auto">
          <div className={`w-1.5 h-1.5 rounded-full ${
            connected ? 'bg-ember' : 'bg-warm-500'
          }`} />
          <span className="text-[10px] text-warm-400">
            {connected ? 'Live' : 'Polling'}
          </span>
        </div>
      </div>

      {/* Job cards */}
      <div className="space-y-2">
        {jobs.map(job => (
          <JobCard key={job.id} job={job} />
        ))}
      </div>
    </div>
  )
}
