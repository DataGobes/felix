export default function TreeRow({ depth, icon, label, meta, selected, dimmed, onClick }) {
  return (
    <button
      onClick={onClick}
      className={`w-full text-left flex items-center gap-1.5 py-1 px-2 text-xs transition-colors ${
        selected
          ? 'bg-ember/[0.08] text-warm-900'
          : dimmed
          ? 'text-warm-400'
          : 'text-warm-600 hover:bg-ember/[0.08] hover:text-warm-900'
      }`}
      style={{ paddingLeft: `${depth * 16 + 8}px` }}
    >
      {icon && <span className="w-4 text-center shrink-0 text-[10px]">{icon}</span>}
      <span className="truncate flex-1">{label}</span>
      {meta && <span className="text-warm-400 text-[10px] shrink-0 ml-auto pl-2">{meta}</span>}
    </button>
  )
}
