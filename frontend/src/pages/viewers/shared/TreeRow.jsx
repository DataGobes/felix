export default function TreeRow({ depth, icon, label, meta, selected, dimmed, onClick }) {
  return (
    <button
      onClick={onClick}
      className={`w-full text-left flex items-center gap-1.5 py-1 px-2 text-xs transition-colors ${
        selected
          ? 'bg-[#00ff41]/10 text-[#c8e6c8]'
          : dimmed
          ? 'text-[#2a4a2a]'
          : 'text-[#5a8a5a] hover:bg-[#00ff41]/10 hover:text-[#8ab88a]'
      }`}
      style={{ paddingLeft: `${depth * 16 + 8}px` }}
    >
      {icon && <span className="w-4 text-center shrink-0 text-[10px]">{icon}</span>}
      <span className="truncate flex-1">{label}</span>
      {meta && <span className="text-[#2a4a2a] text-[10px] shrink-0 ml-auto pl-2">{meta}</span>}
    </button>
  )
}
