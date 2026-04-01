export default function GraphDetailOverlay({ open, onClose, title, children }) {
  return (
    <div
      className="absolute inset-y-0 right-0 w-[480px] max-w-[calc(100%-180px)] z-20 transition-transform duration-300 ease-out"
      style={{ transform: open ? 'translateX(0)' : 'translateX(100%)' }}
    >
      <div className="h-full bg-warm-100 border-l border-warm-200 flex flex-col overflow-hidden">
        <div className="px-4 py-2.5 border-b border-warm-200 flex items-center justify-between shrink-0">
          <h2 className="text-xs font-medium text-warm-600 uppercase tracking-wider">
            {title || 'Detail'}
          </h2>
          <button
            onClick={onClose}
            className="text-warm-500 hover:text-ember transition-colors text-sm leading-none px-1"
          >
            ✕
          </button>
        </div>
        <div className="flex-1 overflow-y-auto overflow-x-hidden [will-change:transform]">
          <div className="break-words [overflow-wrap:anywhere]">
            {children}
          </div>
        </div>
      </div>
    </div>
  )
}
