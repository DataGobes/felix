function Footer() {
  return (
    <footer className="border-t border-warm-200 px-6 py-4 flex items-center justify-end gap-2">
      <div className="w-4 h-4 rounded bg-[#0d0d0d] flex items-center justify-center flex-shrink-0">
        <span className="text-[7px] font-bold text-ember font-mono">&gt;_</span>
      </div>
      <span className="text-xs text-warm-400">
        Built by <a href="https://datagobes.dev" target="_blank" rel="noopener noreferrer" className="text-warm-500 hover:text-ember transition-colors">datagobes.dev</a>
      </span>
    </footer>
  )
}

export default Footer
