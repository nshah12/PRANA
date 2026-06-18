/**
 * Ask PRANA — web version of the mobile ask screen.
 * API: POST /ask { query } → { answer }
 *
 * Privacy: LLM output = insights only. No ₹ figures ever shown.
 */
import { useState, useRef, useEffect } from 'react'
import { Send, Loader2, ShieldCheck } from 'lucide-react'
import { api } from '@/lib/api'
import { useEmpAuthStore } from '@/store/empAuth'

interface Message { id: string; role: 'user' | 'assistant'; text: string }

const SUGGESTIONS = [
  'Does my appraisal reflect in my salary slip?',
  'Is my Form 16 consistent with my payslips?',
  'Am I home loan ready?',
  'Was my bonus paid correctly?',
  'Any employment gaps on record?',
  'Are my ITRs consistent?',
]

export function EmpAsk() {
  const { user } = useEmpAuthStore()
  const name = user?.name?.split(' ')[0] ?? 'there'

  const [messages, setMessages] = useState<Message[]>([
    {
      id: '0', role: 'assistant',
      text: `Hi ${name}! I've processed your documents.\n\nI surface insights, spot discrepancies, and check readiness — your raw figures stay private. Ask me anything about your career documents.`,
    },
  ])
  const [input, setInput] = useState('')
  const [thinking, setThinking] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, thinking])

  async function send(text?: string) {
    const q = (text ?? input).trim()
    if (!q || thinking) return
    setInput('')
    const userMsg: Message = { id: Date.now().toString(), role: 'user', text: q }
    setMessages(prev => [...prev, userMsg])
    setThinking(true)
    try {
      const { data } = await api.post<{ answer: string }>('/ask', { query: q })
      setMessages(prev => [...prev, { id: (Date.now()+1).toString(), role: 'assistant', text: data.answer }])
    } catch (e: any) {
      const status = e.response?.status
      const fallback = status === 429
        ? "You've reached the Ask PRANA limit for this hour. Try again later."
        : status === 504
        ? "The AI is taking longer than expected. Please try again."
        : "Something went wrong. Please try again."
      setMessages(prev => [...prev, { id: (Date.now()+1).toString(), role: 'assistant', text: fallback }])
    } finally { setThinking(false) }
  }

  return (
    <div className="flex flex-col h-screen">
      {/* Header */}
      <div className="bg-slate-900 px-6 py-4 flex items-center gap-3 flex-shrink-0">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-emerald-400 to-cyan-400 flex items-center justify-center">
          <span className="text-emerald-950 font-bold text-sm">✦</span>
        </div>
        <div>
          <p className="text-white font-semibold text-sm">Ask PRANA</p>
          <p className="text-slate-400 text-xs">insights only · figures stay private</p>
        </div>
        <div className="ml-auto bg-emerald-500/10 border border-emerald-500/20 rounded-full px-3 py-1 flex items-center gap-1.5">
          <ShieldCheck size={11} className="text-emerald-400" />
          <span className="text-emerald-400 text-[10px]">No raw figures ever shown</span>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4 bg-slate-50">
        {messages.map(m => (
          <div key={m.id} className={`flex gap-3 ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            {m.role === 'assistant' && (
              <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-emerald-400 to-cyan-400 flex items-center justify-center flex-shrink-0 mt-1">
                <span className="text-emerald-950 font-bold text-xs">✦</span>
              </div>
            )}
            <div className={`max-w-[75%] rounded-2xl px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap ${
              m.role === 'user'
                ? 'bg-indigo-600 text-white rounded-br-sm'
                : 'bg-white border border-slate-200 text-slate-700 rounded-bl-sm'
            }`}>
              {m.text}
            </div>
          </div>
        ))}

        {thinking && (
          <div className="flex gap-3">
            <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-emerald-400 to-cyan-400 flex items-center justify-center flex-shrink-0 mt-1">
              <span className="text-emerald-950 font-bold text-xs">✦</span>
            </div>
            <div className="bg-white border border-slate-200 rounded-2xl rounded-bl-sm px-4 py-3 flex items-center gap-2">
              <Loader2 size={14} className="animate-spin text-indigo-500" />
              <span className="text-slate-400 text-sm">Analysing documents…</span>
            </div>
          </div>
        )}

        {/* Suggestions (first message only) */}
        {messages.length === 1 && (
          <div className="space-y-2 mt-2">
            <p className="text-xs font-medium text-slate-400 uppercase tracking-wide">Suggested</p>
            <div className="flex flex-wrap gap-2">
              {SUGGESTIONS.map(s => (
                <button key={s} onClick={() => send(s)}
                  className="text-xs px-3 py-1.5 bg-white border border-slate-200 rounded-full text-slate-600 hover:border-indigo-300 hover:text-indigo-600 transition-colors">
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="border-t border-slate-200 bg-white px-4 py-3 flex items-end gap-3 flex-shrink-0">
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
          placeholder="Ask about consistency, readiness, growth…"
          rows={1}
          className="flex-1 resize-none border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:border-indigo-400 max-h-32"
          style={{ overflowY: input.split('\n').length > 3 ? 'auto' : 'hidden' }}
        />
        <button onClick={() => send()} disabled={!input.trim() || thinking}
          className="w-10 h-10 rounded-xl bg-indigo-600 flex items-center justify-center text-white hover:bg-indigo-700 disabled:opacity-40 flex-shrink-0">
          <Send size={16} />
        </button>
      </div>
    </div>
  )
}
