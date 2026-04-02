import { useState, useRef, useEffect } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { streamChat } from '../api/client'

function Chat() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [searchingFor, setSearchingFor] = useState(null)
  const [showThinking, setShowThinking] = useState(false)
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
      for await (const event of streamChat(text, history, null, { showThinking })) {
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
    <div className="bg-white rounded-xl shadow-sm overflow-hidden flex flex-col min-h-[400px]" style={{ height: 'calc(100vh - 280px)' }}>
      {/* Header */}
      <div className="px-6 pt-5 pb-4 flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-3">
          <h2 className="text-xs font-medium text-warm-500 uppercase tracking-wider">Chat</h2>
          <span className="px-1.5 py-0.5 text-[10px] font-medium rounded bg-ember/[0.08] text-ember uppercase">
            MiniMax-M2.7
          </span>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-1.5 cursor-pointer">
            <span className="text-[10px] text-warm-500">Thinking</span>
            <button
              onClick={() => setShowThinking(v => !v)}
              className={`relative w-7 h-4 rounded-full transition-colors ${
                showThinking ? 'bg-ember/30' : 'bg-warm-200'
              }`}
            >
              <span className={`absolute top-0.5 w-3 h-3 rounded-full transition-all ${
                showThinking ? 'left-3.5 bg-ember' : 'left-0.5 bg-warm-400'
              }`} />
            </button>
          </label>
          <button
            onClick={handleClear}
            disabled={streaming || messages.length === 0}
            className="text-xs text-warm-500 hover:text-warm-600 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            Clear
          </button>
        </div>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 space-y-4 min-h-0">
        {messages.length === 0 && (
          <div className="flex items-center justify-center h-full">
            <div className="text-center space-y-2">
              <p className="text-sm text-warm-500">Ask anything about your documents</p>
              <p className="text-xs text-warm-400">Felix will search and synthesize answers</p>
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[85%] rounded-lg px-4 py-3 ${
              msg.role === 'user'
                ? 'bg-ember/[0.06] border border-ember/20'
                : 'bg-warm-100 border border-warm-200'
            }`}>
              {/* Message content */}
              <div className={`text-sm leading-relaxed ${
                msg.error ? 'text-red-600' : 'text-warm-600'
              } prose prose-sm prose-warm max-w-none
                prose-headings:text-warm-900 prose-headings:font-semibold prose-headings:mt-3 prose-headings:mb-1
                prose-p:my-1.5 prose-p:leading-relaxed
                prose-strong:text-warm-900 prose-strong:font-semibold
                prose-table:text-xs prose-th:text-warm-500 prose-th:font-medium prose-th:border-warm-200 prose-td:border-warm-200
                prose-li:my-0.5 prose-ul:my-1 prose-ol:my-1
                prose-code:text-ember prose-code:bg-warm-100 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-xs prose-code:before:content-none prose-code:after:content-none
                prose-a:text-ember prose-a:no-underline hover:prose-a:underline`}>
                <Markdown remarkPlugins={[remarkGfm]}>{msg.content}</Markdown>
                {streaming && i === messages.length - 1 && msg.role === 'assistant' && (
                  <span className="inline-block w-1.5 h-4 bg-ember ml-0.5 animate-pulse" />
                )}
              </div>

              {/* Citations */}
              {msg.citations && msg.citations.length > 0 && (
                <div className="mt-3 pt-3 border-t border-warm-200 space-y-1.5">
                  <p className="text-[10px] font-medium text-warm-500 uppercase tracking-wider">Sources</p>
                  {msg.citations.map((cite, j) => (
                    <div key={j} className="flex items-start gap-2 text-xs">
                      <span className="text-ember/60 flex-shrink-0 mt-0.5">[{j + 1}]</span>
                      <div className="min-w-0">
                        <span className="text-warm-600 break-all">{cite.document_path}</span>
                        <p className="text-warm-400 truncate mt-0.5">{cite.content}</p>
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
            <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-warm-bg border border-warm-200 text-xs text-warm-500">
              <span className="flex gap-0.5">
                <span className="typing-dot w-1 h-1 rounded-full bg-ember" style={{ animationDelay: '0s' }} />
                <span className="typing-dot w-1 h-1 rounded-full bg-ember" style={{ animationDelay: '0.2s' }} />
                <span className="typing-dot w-1 h-1 rounded-full bg-ember" style={{ animationDelay: '0.4s' }} />
              </span>
              Searching: {searchingFor}
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <div className="px-6 py-4 border-t border-warm-200 flex-shrink-0">
        <div className="flex gap-2">
          <input
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && !e.shiftKey && handleSend()}
            placeholder="Ask about your documents..."
            disabled={streaming}
            className="flex-1 h-9 px-3 text-sm rounded-lg bg-warm-bg border border-warm-200 text-warm-900 placeholder:text-warm-500 focus:outline-none focus:ring-1 focus:ring-ember/50 disabled:opacity-50 transition-colors"
          />
          <button
            onClick={handleSend}
            disabled={streaming || !input.trim()}
            className="h-9 px-4 text-xs font-medium rounded-lg bg-ember text-white hover:bg-ember/90 disabled:opacity-50 transition-colors"
          >
            {streaming ? 'Thinking...' : 'Send'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default Chat
