import { useState, useRef, useEffect } from 'react'
import { streamChat } from '../api/client'

function Chat() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [searchingFor, setSearchingFor] = useState(null)
  const scrollRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages, searchingFor])

  const handleSend = async () => {
    const text = input.trim()
    if (!text || streaming) return

    const userMsg = { role: 'user', content: text }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setStreaming(true)
    setSearchingFor(null)

    // Build history for the API (exclude citations-only fields)
    const history = messages.map(m => ({ role: m.role, content: m.content }))

    // Add placeholder assistant message
    const assistantIdx = messages.length + 1
    setMessages(prev => [...prev, { role: 'assistant', content: '', citations: [] }])

    try {
      for await (const event of streamChat(text, history)) {
        if (event.type === 'token') {
          setMessages(prev => {
            const updated = [...prev]
            const last = updated[updated.length - 1]
            updated[updated.length - 1] = { ...last, content: last.content + event.content }
            return updated
          })
        } else if (event.type === 'tool_call') {
          setSearchingFor(event.query)
        } else if (event.type === 'tool_result') {
          setSearchingFor(null)
        } else if (event.type === 'done') {
          setMessages(prev => {
            const updated = [...prev]
            const last = updated[updated.length - 1]
            updated[updated.length - 1] = { ...last, citations: event.citations || [] }
            return updated
          })
        }
      }
    } catch (err) {
      setMessages(prev => {
        const updated = [...prev]
        const last = updated[updated.length - 1]
        updated[updated.length - 1] = {
          ...last,
          content: last.content || 'Sorry, something went wrong. Please try again.',
          error: true,
        }
        return updated
      })
    }

    setStreaming(false)
    setSearchingFor(null)
  }

  const handleClear = () => {
    if (streaming) return
    setMessages([])
    setInput('')
    setSearchingFor(null)
  }

  return (
    <div className="bg-[#0a0f0a] rounded-xl shadow-lg shadow-black/20 overflow-hidden flex flex-col min-h-[400px]" style={{ height: 'calc(100vh - 280px)' }}>
      {/* Header */}
      <div className="px-6 pt-5 pb-4 flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-3">
          <h2 className="text-xs font-medium text-[#3d6b3d] uppercase tracking-wider">Chat</h2>
          <span className="px-1.5 py-0.5 text-[10px] font-medium rounded bg-[#00ff41]/10 text-[#00ff41] uppercase">
            gpt-5-mini
          </span>
        </div>
        <button
          onClick={handleClear}
          disabled={streaming || messages.length === 0}
          className="text-xs text-[#3d6b3d] hover:text-[#8ab88a] disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
        >
          Clear
        </button>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 space-y-4 min-h-0">
        {messages.length === 0 && (
          <div className="flex items-center justify-center h-full">
            <div className="text-center space-y-2">
              <p className="text-sm text-[#3d6b3d]">Ask anything about your documents</p>
              <p className="text-xs text-[#2a4a2a]">Felix will search and synthesize answers</p>
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[85%] rounded-lg px-4 py-3 ${
              msg.role === 'user'
                ? 'bg-[#00ff41]/[0.06] border border-[#00ff41]/20'
                : 'bg-[#00ff41]/[0.02] border border-[#0d2b0d]'
            }`}>
              {/* Message content */}
              <p className={`text-sm leading-relaxed whitespace-pre-wrap ${
                msg.error ? 'text-red-400/80' : 'text-[#8ab88a]'
              }`}>
                {msg.content}
                {streaming && i === messages.length - 1 && msg.role === 'assistant' && (
                  <span className="inline-block w-1.5 h-4 bg-[#00ff41] ml-0.5 animate-pulse" />
                )}
              </p>

              {/* Citations */}
              {msg.citations && msg.citations.length > 0 && (
                <div className="mt-3 pt-3 border-t border-[#0d2b0d] space-y-1.5">
                  <p className="text-[10px] font-medium text-[#3d6b3d] uppercase tracking-wider">Sources</p>
                  {msg.citations.map((cite, j) => (
                    <div key={j} className="flex items-start gap-2 text-xs">
                      <span className="text-[#00ff41]/60 flex-shrink-0 mt-0.5">[{j + 1}]</span>
                      <div className="min-w-0">
                        <span className="text-[#00e5ff]/70 break-all">{cite.document_path}</span>
                        <p className="text-[#2a4a2a] truncate mt-0.5">{cite.content}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}

        {/* Tool call indicator */}
        {searchingFor && (
          <div className="flex justify-start">
            <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-[#00ff41]/[0.03] border border-[#0d2b0d] text-xs text-[#3d6b3d]">
              <span className="flex gap-0.5">
                <span className="typing-dot w-1 h-1 rounded-full bg-[#00ff41]" style={{ animationDelay: '0s' }} />
                <span className="typing-dot w-1 h-1 rounded-full bg-[#00ff41]" style={{ animationDelay: '0.2s' }} />
                <span className="typing-dot w-1 h-1 rounded-full bg-[#00ff41]" style={{ animationDelay: '0.4s' }} />
              </span>
              Searching: {searchingFor}
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <div className="px-6 py-4 border-t border-[#0d2b0d] flex-shrink-0">
        <div className="flex gap-2">
          <input
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && !e.shiftKey && handleSend()}
            placeholder="Ask about your documents..."
            disabled={streaming}
            className="flex-1 h-9 px-3 text-sm rounded-lg bg-[#00ff41]/[0.03] border border-[#0d2b0d] text-[#c8e6c8] placeholder:text-[#3d6b3d] focus:outline-none focus:ring-1 focus:ring-[#00ff41]/50 disabled:opacity-50 transition-colors"
          />
          <button
            onClick={handleSend}
            disabled={streaming || !input.trim()}
            className="h-9 px-4 text-xs font-medium rounded-lg bg-[#00ff41] text-black hover:bg-[#00cc33] disabled:opacity-50 transition-colors"
          >
            {streaming ? 'Thinking...' : 'Send'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default Chat
