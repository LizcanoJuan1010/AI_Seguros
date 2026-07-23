/**
 * Panel de historial de conversaciones (patrón portado de Paloma):
 * lista todas las sesiones guardadas por el servicio IA con un preview,
 * y permite abrir cualquiera para releer los mensajes. Solo lectura —
 * es la memoria auditable del asistente "por si acaso".
 */
import { useEffect, useState } from 'react'
import { Icon } from '../../components/ui/Icon'
import { MessageMarkdown } from './MessageMarkdown'

type SessionRow = { session_id: string; mensajes: number; preview: string }
type HistoryMsg = { role: 'user' | 'assistant'; content: string }

type Props = {
  open: boolean
  onClose: () => void
  /** Sesión activa del chat — se resalta como "actual". */
  currentSessionId: string
}

export function ChatHistoryPanel({ open, onClose, currentSessionId }: Props) {
  const [sessions, setSessions] = useState<SessionRow[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<SessionRow | null>(null)
  const [messages, setMessages] = useState<HistoryMsg[]>([])

  useEffect(() => {
    if (!open) return
    setLoading(true)
    setError(null)
    setSelected(null)
    fetch('/api/assistant/sessions?limit=50')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((data: SessionRow[]) => setSessions(data))
      .catch(() => setError('No se pudo cargar el historial.'))
      .finally(() => setLoading(false))
  }, [open])

  const openSession = (s: SessionRow) => {
    setSelected(s)
    setMessages([])
    fetch(`/api/assistant/history/${encodeURIComponent(s.session_id)}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((data: HistoryMsg[]) => setMessages(data))
      .catch(() => setError('No se pudo abrir la conversación.'))
  }

  if (!open) return null

  return (
    <>
      {/* Telón: clic afuera cierra */}
      <div
        className="fixed inset-0 z-[70] bg-forest-deep/20 backdrop-blur-[2px]"
        onClick={onClose}
        aria-hidden
      />
      <aside className="fixed inset-y-0 right-0 z-[80] flex w-full max-w-md flex-col border-l border-outline-variant bg-surface shadow-2xl">
        <header className="glass-header flex items-center justify-between border-b border-outline-variant px-4 py-3">
          <div className="flex items-center gap-2">
            {selected && (
              <button
                type="button"
                onClick={() => setSelected(null)}
                aria-label="Volver a la lista"
                className="flex size-9 items-center justify-center rounded-full text-on-surface-variant hover:bg-surface-variant"
              >
                <Icon name="arrow_back" className="text-[20px]" />
              </button>
            )}
            <h3 className="text-label-md font-bold text-on-surface">
              {selected ? 'Conversación' : 'Historial de conversaciones'}
            </h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar historial"
            className="flex size-9 items-center justify-center rounded-full text-on-surface-variant hover:bg-surface-variant"
          >
            <Icon name="close" className="text-[20px]" />
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto p-3">
          {error && (
            <p className="rounded-md bg-error-container/50 px-3 py-2 text-label-md text-on-error-container">
              {error}
            </p>
          )}

          {!selected ? (
            loading ? (
              <p className="px-2 py-6 text-center text-label-md text-on-surface-variant">
                Cargando historial…
              </p>
            ) : sessions.length === 0 ? (
              <p className="px-2 py-6 text-center text-label-md text-on-surface-variant">
                Aún no hay conversaciones guardadas.
              </p>
            ) : (
              <ul className="flex flex-col gap-1.5">
                {sessions.map((s) => {
                  // El servicio guarda la sesión como `<tenant>:<session_id>`.
                  const isCurrent =
                    s.session_id === currentSessionId ||
                    s.session_id.endsWith(`:${currentSessionId}`)
                  return (
                    <li key={s.session_id}>
                      <button
                        type="button"
                        onClick={() => openSession(s)}
                        className="w-full rounded-xl border border-outline-variant/50 bg-surface-container-lowest px-4 py-3 text-left transition-colors hover:border-primary/40 hover:bg-surface-container-low"
                      >
                        <span className="flex items-center justify-between gap-2">
                          <span className="truncate text-label-md font-bold text-on-surface">
                            {s.preview}
                          </span>
                          {isCurrent && (
                            <span className="shrink-0 rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-bold uppercase text-primary">
                              actual
                            </span>
                          )}
                        </span>
                        <span className="mt-0.5 block text-label-sm text-on-surface-variant">
                          {s.mensajes} mensajes · {s.session_id.slice(0, 18)}…
                        </span>
                      </button>
                    </li>
                  )
                })}
              </ul>
            )
          ) : messages.length === 0 ? (
            <p className="px-2 py-6 text-center text-label-md text-on-surface-variant">
              Cargando conversación…
            </p>
          ) : (
            <div className="flex flex-col gap-3">
              {messages.map((m, i) => (
                <div
                  key={i}
                  className={`max-w-[88%] rounded-2xl p-3 text-body-md shadow-sm ${
                    m.role === 'user'
                      ? 'self-end rounded-tr-none bg-primary-container text-white'
                      : 'self-start rounded-tl-none border border-outline-variant/40 bg-white text-on-surface'
                  }`}
                >
                  {m.role === 'assistant' ? (
                    <MessageMarkdown content={m.content} />
                  ) : (
                    <p className="whitespace-pre-wrap">{m.content}</p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </aside>
    </>
  )
}
