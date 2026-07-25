/**
 * Navegador de conversaciones (estilo ChatGPT/Gemini).
 *
 * Reemplaza al viejo lector read-only: aquí NO se previsualiza la conversación
 * dentro del panel — al seleccionarla se ENTRA a ella en la vista principal del
 * chat (el panel se cierra). Sirve a dos públicos:
 *
 *  - Cliente / todos: "Tus conversaciones" = los chats de este dispositivo
 *    (índice local en lib/chatSessions.ts) + "Nueva conversación".
 *  - Staff (canAudit): además, "Auditoría" = todas las conversaciones guardadas
 *    en el servidor (`GET /api/assistant/sessions`, protegido con Bearer).
 */
import { useEffect, useState } from 'react'
import { Icon } from '../../components/ui/Icon'
import { authHeaders } from '../../lib/authFetch'
import type { ChatMeta } from '../../lib/chatSessions'

type SessionRow = { session_id: string; mensajes: number; preview: string }

type Props = {
  open: boolean
  onClose: () => void
  /** Conversaciones de este dispositivo (índice local). */
  chats: ChatMeta[]
  /** session_id activo — se resalta en la lista. */
  activeId: string
  onNewChat: () => void
  onSelectChat: (id: string) => void
  onDeleteChat: (id: string) => void
  /** Staff: habilita la sección de auditoría (todas las conversaciones). */
  canAudit: boolean
  /** Entra a una conversación de auditoría por su clave `<tenant>:<session>`. */
  onEnterGlobal: (storageKey: string) => void
}

/** "hace 3 min" / "hace 2 h" / "ayer" / "12 mar" — compacto y en español. */
function relativeTime(ts: number): string {
  const diff = Date.now() - ts
  const min = Math.round(diff / 60000)
  if (min < 1) return 'ahora'
  if (min < 60) return `hace ${min} min`
  const h = Math.round(min / 60)
  if (h < 24) return `hace ${h} h`
  const d = Math.round(h / 24)
  if (d === 1) return 'ayer'
  if (d < 7) return `hace ${d} d`
  return new Date(ts).toLocaleDateString('es-CO', { day: 'numeric', month: 'short' })
}

export function ChatHistoryPanel({
  open,
  onClose,
  chats,
  activeId,
  onNewChat,
  onSelectChat,
  onDeleteChat,
  canAudit,
  onEnterGlobal,
}: Props) {
  const [auditOpen, setAuditOpen] = useState(false)
  const [sessions, setSessions] = useState<SessionRow[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Carga perezosa del listado global: solo cuando staff abre la auditoría.
  useEffect(() => {
    if (!open || !auditOpen) return
    setLoading(true)
    setError(null)
    fetch('/api/assistant/sessions?limit=50', { headers: authHeaders() })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((data: SessionRow[]) => setSessions(data))
      .catch(() => setError('No se pudo cargar la auditoría.'))
      .finally(() => setLoading(false))
  }, [open, auditOpen])

  if (!open) return null

  return (
    <>
      <div
        className="fixed inset-0 z-[70] bg-forest-deep/20 backdrop-blur-[2px]"
        onClick={onClose}
        aria-hidden
      />
      <aside className="fixed inset-y-0 right-0 z-[80] flex w-full max-w-md flex-col border-l border-outline-variant bg-surface shadow-2xl">
        <header className="glass-header flex items-center justify-between border-b border-outline-variant px-4 py-3">
          <h3 className="text-label-md font-bold text-on-surface">Conversaciones</h3>
          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar"
            className="flex size-9 items-center justify-center rounded-full text-on-surface-variant hover:bg-surface-variant"
          >
            <Icon name="close" className="text-[20px]" />
          </button>
        </header>

        <div className="border-b border-outline-variant/60 p-3">
          <button
            type="button"
            onClick={() => {
              onNewChat()
              onClose()
            }}
            className="flex w-full items-center gap-2 rounded-xl bg-primary px-4 py-3 text-label-md font-bold text-on-primary shadow-sm transition-colors hover:bg-primary/90"
          >
            <Icon name="add" className="text-[20px]" />
            Nueva conversación
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-3">
          <p className="px-1 pb-2 text-label-sm font-bold uppercase tracking-wide text-on-surface-variant">
            Tus conversaciones
          </p>

          {chats.length === 0 ? (
            <p className="px-2 py-6 text-center text-label-md text-on-surface-variant">
              Aún no tienes conversaciones. Empieza a chatear y aparecerán aquí.
            </p>
          ) : (
            <ul className="flex flex-col gap-1.5">
              {chats.map((c) => {
                const isCurrent = c.id === activeId
                return (
                  <li key={c.id} className="group relative">
                    <button
                      type="button"
                      onClick={() => {
                        onSelectChat(c.id)
                        onClose()
                      }}
                      className={`w-full rounded-xl border px-4 py-3 pr-11 text-left transition-colors ${
                        isCurrent
                          ? 'border-primary/40 bg-primary/5'
                          : 'border-outline-variant/50 bg-surface-container-lowest hover:border-primary/40 hover:bg-surface-container-low'
                      }`}
                    >
                      <span className="flex items-center justify-between gap-2">
                        <span className="truncate text-label-md font-bold text-on-surface">
                          {c.title || 'Conversación nueva'}
                        </span>
                        {isCurrent && (
                          <span className="shrink-0 rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-bold uppercase text-primary">
                            actual
                          </span>
                        )}
                      </span>
                      <span className="mt-0.5 block text-label-sm text-on-surface-variant">
                        {relativeTime(c.updatedAt)}
                      </span>
                    </button>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation()
                        onDeleteChat(c.id)
                      }}
                      aria-label={`Eliminar "${c.title || 'conversación'}"`}
                      title="Quitar de la lista"
                      className="absolute right-2 top-1/2 flex size-8 -translate-y-1/2 items-center justify-center rounded-full text-on-surface-variant opacity-0 transition-opacity hover:bg-error-container/60 hover:text-error focus:opacity-100 group-hover:opacity-100"
                    >
                      <Icon name="delete" className="text-[18px]" />
                    </button>
                  </li>
                )
              })}
            </ul>
          )}

          {canAudit && (
            <div className="mt-4 border-t border-outline-variant/50 pt-3">
              <button
                type="button"
                onClick={() => setAuditOpen((v) => !v)}
                className="flex w-full items-center justify-between rounded-lg px-1 py-2 text-label-sm font-bold uppercase tracking-wide text-on-surface-variant hover:text-primary"
              >
                <span className="flex items-center gap-1.5">
                  <Icon name="shield_person" className="text-[18px]" />
                  Auditoría · todas
                </span>
                <Icon
                  name={auditOpen ? 'expand_less' : 'expand_more'}
                  className="text-[20px]"
                />
              </button>

              {auditOpen && (
                <div className="mt-2">
                  {error && (
                    <p className="rounded-md bg-error-container/50 px-3 py-2 text-label-sm text-on-error-container">
                      {error}
                    </p>
                  )}
                  {loading ? (
                    <p className="px-2 py-4 text-center text-label-sm text-on-surface-variant">
                      Cargando…
                    </p>
                  ) : sessions.length === 0 && !error ? (
                    <p className="px-2 py-4 text-center text-label-sm text-on-surface-variant">
                      No hay conversaciones guardadas.
                    </p>
                  ) : (
                    <ul className="flex flex-col gap-1.5">
                      {sessions.map((s) => (
                        <li key={s.session_id}>
                          <button
                            type="button"
                            onClick={() => {
                              onEnterGlobal(s.session_id)
                              onClose()
                            }}
                            className="w-full rounded-xl border border-outline-variant/50 bg-surface-container-lowest px-4 py-3 text-left transition-colors hover:border-primary/40 hover:bg-surface-container-low"
                          >
                            <span className="block truncate text-label-md font-bold text-on-surface">
                              {s.preview}
                            </span>
                            <span className="mt-0.5 block text-label-sm text-on-surface-variant">
                              {s.mensajes} mensajes · {s.session_id.slice(0, 18)}…
                            </span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </aside>
    </>
  )
}
