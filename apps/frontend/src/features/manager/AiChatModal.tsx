/**
 * Modal de chat con el agente IA REAL (rol gerente) reutilizable en el
 * dashboard. Habla con `POST /api/chat` del servicio IA usando el JWT del
 * gerente logueado (resolve_identity → rol gerente), por lo que el agente
 * puede usar sus herramientas reales (`obtener_insights`, `listar_leads`…) y
 * fundamentar sus respuestas en datos del negocio — nada quemado.
 *
 * Se abre con un `initialPrompt` que se envía solo; luego admite preguntas de
 * seguimiento (multiturno: el servicio mantiene el historial por session_id).
 */
import { useEffect, useRef, useState } from 'react'
import { Icon } from '../../components/ui/Icon'
import { MessageMarkdown } from '../assistant/MessageMarkdown'
import { authHeaders } from '../../lib/authFetch'

type Msg = { role: 'user' | 'assistant'; text: string }

type Props = {
  open: boolean
  onClose: () => void
  title: string
  subtitle?: string
  /** Se envía automáticamente al abrir. No se muestra como burbuja del usuario. */
  initialPrompt: string
}

let seq = 0

export function AiChatModal({ open, onClose, title, subtitle, initialPrompt }: Props) {
  const [messages, setMessages] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const sessionRef = useRef<string>('')
  const scrollRef = useRef<HTMLDivElement>(null)
  const sentInitial = useRef(false)

  const send = async (text: string, hideUser = false) => {
    if (!text.trim() || busy) return
    setBusy(true)
    setError(null)
    if (!hideUser) setMessages((m) => [...m, { role: 'user', text }])
    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ session_id: sessionRef.current, message: text }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = (await res.json()) as { reply?: string }
      setMessages((m) => [
        ...m,
        { role: 'assistant', text: data.reply || 'Sin respuesta.' },
      ])
    } catch {
      setError('No se pudo consultar a la IA. ¿Sesión de gerente activa?')
    } finally {
      setBusy(false)
    }
  }

  // Al abrir: sesión nueva, limpia, y dispara el prompt inicial una sola vez.
  useEffect(() => {
    if (!open) {
      sentInitial.current = false
      return
    }
    seq += 1
    sessionRef.current = `mgr-chat-${Date.now()}-${seq}`
    setMessages([])
    setInput('')
    setError(null)
    if (!sentInitial.current) {
      sentInitial.current = true
      void send(initialPrompt, true)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- solo al abrir
  }, [open])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [messages, busy])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-forest-deep/30 backdrop-blur-sm sm:items-center"
      onClick={onClose}
    >
      <div
        className="flex h-[85vh] w-full max-w-2xl flex-col overflow-hidden rounded-t-2xl bg-surface-container-lowest shadow-2xl sm:h-[80vh] sm:rounded-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center gap-3 border-b border-outline-variant bg-white p-4">
          <span className="flex size-9 items-center justify-center rounded-full bg-primary/10 text-primary">
            <Icon name="smart_toy" className="text-[20px]" />
          </span>
          <div className="min-w-0 flex-1">
            <h3 className="truncate text-base font-bold text-on-surface">{title}</h3>
            {subtitle && (
              <p className="truncate text-xs text-on-surface-variant">{subtitle}</p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex size-8 items-center justify-center rounded-full hover:bg-surface-variant"
            aria-label="Cerrar"
          >
            <Icon name="close" />
          </button>
        </header>

        <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto p-4">
          {messages.map((m, i) => (
            <div
              key={i}
              className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={
                  m.role === 'user'
                    ? 'max-w-[85%] rounded-2xl rounded-tr-none bg-primary px-4 py-2.5 text-sm text-on-primary'
                    : 'max-w-[92%] rounded-2xl rounded-tl-none bg-surface-container px-4 py-3 text-sm text-on-surface'
                }
              >
                {m.role === 'assistant' ? (
                  <MessageMarkdown content={m.text} />
                ) : (
                  m.text
                )}
              </div>
            </div>
          ))}
          {busy && (
            <div className="flex items-center gap-2 text-sm text-on-surface-variant">
              <Icon name="smart_toy" className="text-[18px] text-primary" />
              <span className="flex gap-1">
                <span className="size-1.5 animate-bounce rounded-full bg-primary [animation-delay:-0.2s]" />
                <span className="size-1.5 animate-bounce rounded-full bg-primary [animation-delay:-0.1s]" />
                <span className="size-1.5 animate-bounce rounded-full bg-primary" />
              </span>
              La IA está analizando datos reales…
            </div>
          )}
          {error && (
            <p className="rounded-lg bg-error-container/40 p-3 text-sm text-on-error-container">
              {error}
            </p>
          )}
        </div>

        <form
          className="flex items-center gap-2 border-t border-outline-variant bg-white p-3"
          onSubmit={(e) => {
            e.preventDefault()
            const text = input.trim()
            if (!text) return
            setInput('')
            void send(text)
          }}
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Pregúntale algo más a la IA…"
            className="flex-1 rounded-full border border-outline-variant bg-surface-container-lowest px-4 py-2.5 text-sm outline-none focus:border-primary"
          />
          <button
            type="submit"
            disabled={busy || !input.trim()}
            className="flex size-10 items-center justify-center rounded-full bg-primary text-on-primary transition-colors hover:bg-primary/90 disabled:opacity-40"
            aria-label="Enviar"
          >
            <Icon name="send" className="text-[18px]" />
          </button>
        </form>
      </div>
    </div>
  )
}
