import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { getStoredTenantId } from '../../lib/api'
import { authHeaders } from '../../lib/authFetch'
import { getDeviceId } from '../../lib/clientIdentity'
import {
  type ChatMeta,
  deleteChat,
  getActiveChatId,
  hasChat,
  listChats,
  newChatId,
  setActiveChatId,
  touchChat,
} from '../../lib/chatSessions'
import { useTenant } from '../../tenant/TenantContext'

/**
 * Hook de chat con streaming SSE contra el servicio IA (FastAPI).
 *
 * Contrato (docs/FUSION.md → "Contrato SSE"):
 *   POST /api/assistant/chat/stream
 *   body: { session_id, message, phone?, manager_key? }
 *   Respuesta: text/event-stream con frames `event:` / `data:` (JSON por línea).
 *
 * Eventos soportados: thinking | token | tool_start | tool_result |
 * quick_replies | document | checkout_step | policy | claim | underwriting |
 * done | error.
 *
 * El render de tokens se batchea con requestAnimationFrame para evitar un
 * re-render por token. Degrada sin romper si el backend no responde.
 */

export type ToolCall = {
  id: string
  tool: string
  args?: Record<string, unknown>
  status: 'running' | 'done'
  summary?: string
  meta?: Record<string, unknown>
}

export type AssistantDocument = {
  download_url: string
  title: string
}

/** Pasos del flujo de cierre autónomo (evento `checkout_step`). */
export type CheckoutStep = 'datos' | 'consentimiento' | 'pago' | 'emision'

/** Estado del cierre asociado a un mensaje del asistente. */
export type CheckoutState = {
  step: CheckoutStep
  /** Campos que el asistente está pidiendo en este paso (opcional). */
  fields?: string[]
}

/** Póliza emitida (evento `policy`) — el momento "ya quedé asegurada". */
export type AssistantPolicy = {
  policyNumber: string
  download_url: string
  title: string
}

/** Reclamo / siniestro (evento `claim`, FNOL o consulta de estado). */
export type AssistantClaim = {
  claimNumber: string
  status: string
  tipo?: string | null
  poliza?: string | null
  documentos_requeridos?: string[]
  title: string
}

/** Decisión de underwriting (evento `underwriting`). */
export type AssistantUnderwriting = {
  decision: 'AUTO_APPROVE' | 'REFER' | 'DECLINE'
  label: string
  reasons: string[]
  segmento_riesgo?: string | null
}

/** Estado del pago real (evento `payment_link`, pasarela Polar o modo demo). */
export type PaymentStatus =
  | 'PENDING'
  | 'APPROVED'
  | 'DECLINED'
  | 'VOIDED'
  | 'ERROR'
  | 'REFUND_REQUESTED'

export type AssistantPayment = {
  reference: string
  /** URL del checkout seguro de Polar (null en modo demo). */
  checkout_url?: string | null
  amount_cop?: number
  concept?: string
  status: PaymentStatus
  provider?: string
  demo?: boolean
}

export type ChatRole = 'user' | 'assistant'

export type ChatMessage = {
  id: string
  role: ChatRole
  content: string
  /** Texto del indicador "pensando" mientras no llegan tokens. */
  thinking?: string
  tools: ToolCall[]
  quickReplies: string[]
  documents: AssistantDocument[]
  /** Paso actual del flujo de cierre (último `checkout_step` recibido). */
  checkout?: CheckoutState
  /** Pago real en curso asociado a este mensaje (evento `payment_link`). */
  payment?: AssistantPayment
  /** Póliza emitida asociada a este mensaje (evento `policy`). */
  policy?: AssistantPolicy
  /** Reclamo reportado/consultado en este mensaje (evento `claim`). */
  claim?: AssistantClaim
  /** Decisión de underwriting de este turno (evento `underwriting`). */
  underwriting?: AssistantUnderwriting
  error?: string
  /** true cuando el stream de este mensaje terminó (done / error / corte). */
  done: boolean
}

type SseEvent =
  | { event: 'thinking'; data: { text?: string } }
  | { event: 'token'; data: { text?: string } }
  | { event: 'tool_start'; data: { tool: string; args?: Record<string, unknown> } }
  | {
      event: 'tool_result'
      data: { tool: string; summary?: string; meta?: Record<string, unknown> }
    }
  | { event: 'quick_replies'; data: { items?: string[] } }
  | { event: 'document'; data: { download_url: string; title?: string } }
  | { event: 'checkout_step'; data: { step: CheckoutStep; fields?: string[] } }
  | { event: 'payment_link'; data: AssistantPayment }
  | {
      event: 'policy'
      data: { policyNumber: string; download_url: string; title?: string }
    }
  | { event: 'claim'; data: Partial<AssistantClaim> }
  | { event: 'underwriting'; data: Partial<AssistantUnderwriting> }
  | { event: 'done'; data: { session_id?: string } }
  | { event: 'error'; data: { message?: string } }
  | { event: string; data: unknown }

const STREAM_ENDPOINT = '/api/assistant/chat/stream'
// Tenant (organización) activo. En producción viene del equipo del usuario autenticado;
// por defecto, el tenant demo de Colsubsidio. Configurable con VITE_TENANT_ID.
const TENANT_ID =
  (import.meta.env?.VITE_TENANT_ID as string | undefined) ||
  '11111111-1111-1111-1111-111111111111'

/** Tenant efectivo: el equipo elegido en el TeamSwitcher, o el demo por defecto. */
function effectiveTenantId(): string {
  return getStoredTenantId() || TENANT_ID
}

function makeId(prefix: string): string {
  const rnd =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : Math.random().toString(36).slice(2)
  return `${prefix}_${rnd}`
}

type RawHistoryMsg = { role?: unknown; content?: unknown }

/** Convierte las filas de `/api/assistant/history` en mensajes del chat. */
function mapHistoryRows(rows: unknown): ChatMessage[] {
  if (!Array.isArray(rows)) return []
  const out: ChatMessage[] = []
  for (const r of rows as RawHistoryMsg[]) {
    const role = r?.role
    const content = r?.content
    if (
      (role === 'user' || role === 'assistant') &&
      typeof content === 'string' &&
      content.trim().length > 0
    ) {
      out.push({
        id: makeId('hist'),
        role,
        content,
        tools: [],
        quickReplies: [],
        documents: [],
        done: true,
      })
    }
  }
  return out
}

/** Parsea un bloque SSE (líneas separadas por \n) en {event, data}. */
function parseFrame(raw: string): SseEvent | null {
  let event = 'message'
  const dataLines: string[] = []
  for (const line of raw.split('\n')) {
    if (line.startsWith(':')) continue // comentario / heartbeat
    if (line.startsWith('event:')) {
      event = line.slice(6).trim()
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).replace(/^ /, ''))
    }
  }
  if (dataLines.length === 0) return null
  const payload = dataLines.join('\n')
  try {
    return { event, data: JSON.parse(payload) } as SseEvent
  } catch {
    return { event, data: payload }
  }
}

export type SendOptions = {
  phone?: string
  managerKey?: string
}

export function useAssistantChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  // sessionId = conversación activa (rotable con "nueva conversación").
  // chats = índice de conversaciones del dispositivo (la lista estilo ChatGPT).
  const [sessionId, setSessionId] = useState<string>(() =>
    typeof window === 'undefined'
      ? makeId('sess')
      : getActiveChatId(effectiveTenantId()),
  )
  const [chats, setChats] = useState<ChatMeta[]>(() =>
    typeof window === 'undefined' ? [] : listChats(effectiveTenantId()),
  )

  const { teamId } = useTenant()
  // La "cuenta" anónima nace al ENTRAR al chat (no al primer mensaje): así el
  // dispositivo ya queda identificado aunque el cliente solo mire.
  const deviceId = useMemo(getDeviceId, [])

  // --- refs de streaming ---
  const pendingTokensRef = useRef('')
  const rafRef = useRef<number | null>(null)
  const currentAssistantIdRef = useRef<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const streamingRef = useRef(false)

  const patchMessage = useCallback(
    (id: string, patch: (m: ChatMessage) => ChatMessage) => {
      setMessages((prev) => prev.map((m) => (m.id === id ? patch(m) : m)))
    },
    [],
  )

  const flushTokens = useCallback(() => {
    const pending = pendingTokensRef.current
    const id = currentAssistantIdRef.current
    if (!pending || !id) return
    pendingTokensRef.current = ''
    patchMessage(id, (m) => ({
      ...m,
      content: m.content + pending,
      thinking: undefined,
    }))
  }, [patchMessage])

  const scheduleFlush = useCallback(() => {
    if (rafRef.current != null) return
    if (typeof requestAnimationFrame === 'undefined') {
      flushTokens()
      return
    }
    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = null
      flushTokens()
    })
  }, [flushTokens])

  const finalize = useCallback(() => {
    if (rafRef.current != null) {
      cancelAnimationFrame(rafRef.current)
      rafRef.current = null
    }
    flushTokens()
    const id = currentAssistantIdRef.current
    if (id) patchMessage(id, (m) => ({ ...m, thinking: undefined, done: true }))
    currentAssistantIdRef.current = null
    abortRef.current = null
    streamingRef.current = false
    setIsStreaming(false)
  }, [flushTokens, patchMessage])

  const dispatch = useCallback(
    (frame: SseEvent) => {
      const id = currentAssistantIdRef.current
      if (!id) return
      switch (frame.event) {
        case 'thinking': {
          const text = (frame.data as { text?: string })?.text ?? 'Pensando...'
          patchMessage(id, (m) =>
            m.content ? m : { ...m, thinking: text },
          )
          break
        }
        case 'token': {
          const text = (frame.data as { text?: string })?.text ?? ''
          if (!text) break
          pendingTokensRef.current += text
          scheduleFlush()
          break
        }
        case 'tool_start': {
          const d = frame.data as { tool: string; args?: Record<string, unknown> }
          patchMessage(id, (m) => ({
            ...m,
            thinking: undefined,
            tools: [
              ...m.tools,
              {
                id: makeId('tool'),
                tool: d.tool,
                args: d.args,
                status: 'running',
              },
            ],
          }))
          break
        }
        case 'tool_result': {
          const d = frame.data as {
            tool: string
            summary?: string
            meta?: Record<string, unknown>
          }
          patchMessage(id, (m) => {
            const tools = [...m.tools]
            // Marca como done la última tool en curso con ese nombre.
            for (let i = tools.length - 1; i >= 0; i -= 1) {
              if (tools[i].tool === d.tool && tools[i].status === 'running') {
                tools[i] = {
                  ...tools[i],
                  status: 'done',
                  summary: d.summary,
                  meta: d.meta,
                }
                return { ...m, tools }
              }
            }
            // Sin tool_start previo: crea una ya completada.
            tools.push({
              id: makeId('tool'),
              tool: d.tool,
              status: 'done',
              summary: d.summary,
              meta: d.meta,
            })
            return { ...m, tools }
          })
          break
        }
        case 'quick_replies': {
          const items = (frame.data as { items?: string[] })?.items ?? []
          patchMessage(id, (m) => ({ ...m, quickReplies: items }))
          break
        }
        case 'document': {
          const d = frame.data as { download_url: string; title?: string }
          if (!d?.download_url) break
          patchMessage(id, (m) => ({
            ...m,
            documents: [
              ...m.documents,
              { download_url: d.download_url, title: d.title ?? 'Documento' },
            ],
          }))
          break
        }
        case 'checkout_step': {
          const d = frame.data as { step?: CheckoutStep; fields?: string[] }
          const step = d?.step
          if (!step) break
          patchMessage(id, (m) => ({
            ...m,
            thinking: undefined,
            checkout: { step, fields: d.fields },
          }))
          break
        }
        case 'payment_link': {
          const d = frame.data as Partial<AssistantPayment>
          if (!d?.reference) break
          patchMessage(id, (m) => ({
            ...m,
            thinking: undefined,
            // Merge con el pago previo: una actualización de estado (p. ej.
            // verificar_pago) puede venir sin checkout_url y no debe borrarlo.
            payment: {
              ...(m.payment?.reference === d.reference ? m.payment : {}),
              ...Object.fromEntries(
                Object.entries(d).filter(([, v]) => v !== null && v !== undefined),
              ),
              reference: d.reference,
              status: (d.status ?? m.payment?.status ?? 'PENDING') as PaymentStatus,
            } as AssistantPayment,
          }))
          break
        }
        case 'policy': {
          const d = frame.data as {
            policyNumber?: string
            download_url?: string
            title?: string
          }
          if (!d?.policyNumber || !d?.download_url) break
          patchMessage(id, (m) => ({
            ...m,
            thinking: undefined,
            policy: {
              policyNumber: d.policyNumber as string,
              download_url: d.download_url as string,
              title: d.title ?? 'Póliza vigente',
            },
          }))
          break
        }
        case 'claim': {
          const d = frame.data as Partial<AssistantClaim>
          if (!d?.claimNumber) break
          patchMessage(id, (m) => ({
            ...m,
            thinking: undefined,
            claim: {
              claimNumber: d.claimNumber as string,
              status: d.status ?? 'REPORTADO',
              tipo: d.tipo,
              poliza: d.poliza,
              documentos_requeridos: d.documentos_requeridos ?? [],
              title: d.title ?? 'Reclamo registrado',
            },
          }))
          break
        }
        case 'underwriting': {
          const d = frame.data as Partial<AssistantUnderwriting>
          if (!d?.decision) break
          patchMessage(id, (m) => ({
            ...m,
            thinking: undefined,
            underwriting: {
              decision: d.decision as AssistantUnderwriting['decision'],
              label: d.label ?? d.decision ?? '',
              reasons: d.reasons ?? [],
              segmento_riesgo: d.segmento_riesgo,
            },
          }))
          break
        }
        case 'error': {
          const message =
            (frame.data as { message?: string })?.message ??
            'Ocurrió un error en el asistente.'
          flushTokens()
          patchMessage(id, (m) => ({ ...m, error: message, thinking: undefined }))
          break
        }
        case 'done': {
          finalize()
          break
        }
        default:
          break
      }
    },
    [finalize, flushTokens, patchMessage, scheduleFlush],
  )

  const sendMessage = useCallback(
    async (text: string, options?: SendOptions) => {
      const trimmed = text.trim()
      if (!trimmed || streamingRef.current) return

      const userMsg: ChatMessage = {
        id: makeId('user'),
        role: 'user',
        content: trimmed,
        tools: [],
        quickReplies: [],
        documents: [],
        done: true,
      }
      const assistantId = makeId('assistant')
      const assistantMsg: ChatMessage = {
        id: assistantId,
        role: 'assistant',
        content: '',
        thinking: 'Pensando...',
        tools: [],
        quickReplies: [],
        documents: [],
        done: false,
      }

      // Limpia quick replies del turno anterior al enviar uno nuevo.
      setMessages((prev) => [
        ...prev.map((m) => (m.quickReplies.length ? { ...m, quickReplies: [] } : m)),
        userMsg,
        assistantMsg,
      ])

      // Índice de chats: al primer mensaje la conversación entra a la lista con
      // su título (ese mensaje); en los siguientes solo sube su recencia.
      {
        const tenant = effectiveTenantId()
        const isFirst = !hasChat(tenant, sessionId)
        touchChat(tenant, sessionId, isFirst ? { title: trimmed } : undefined)
        setChats(listChats(tenant))
      }

      currentAssistantIdRef.current = assistantId
      pendingTokensRef.current = ''
      streamingRef.current = true
      setIsStreaming(true)

      const controller = new AbortController()
      abortRef.current = controller

      try {
        const res = await fetch(STREAM_ENDPOINT, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Accept: 'text/event-stream',
            // El tenant ya NO se manda como header: sale del JWT. Se envía el
            // Bearer y el backend/IA extrae teamId + role de los claims.
            ...authHeaders(),
          },
          body: JSON.stringify({
            session_id: sessionId,
            message: trimmed,
            // Identidad durable del cliente anónimo: ancla memoria y leads al
            // dispositivo, no a la conversación (sobrevive a "chat nuevo").
            device_id: deviceId,
            ...(options?.phone ? { phone: options.phone } : {}),
            ...(options?.managerKey ? { manager_key: options.managerKey } : {}),
          }),
          signal: controller.signal,
        })

        if (!res.ok || !res.body) {
          patchMessage(assistantId, (m) => ({
            ...m,
            error: `No se pudo conectar con el asistente (HTTP ${res.status}).`,
            thinking: undefined,
          }))
          finalize()
          return
        }

        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        // Lectura incremental del ReadableStream.
        for (;;) {
          const { value, done } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })

          // Los frames SSE se separan por línea en blanco (\n\n).
          let sep = buffer.indexOf('\n\n')
          while (sep !== -1) {
            const rawFrame = buffer.slice(0, sep)
            buffer = buffer.slice(sep + 2)
            const frame = parseFrame(rawFrame)
            if (frame) dispatch(frame)
            sep = buffer.indexOf('\n\n')
          }
        }

        // Frame residual sin \n\n final.
        const tail = buffer.trim()
        if (tail) {
          const frame = parseFrame(tail)
          if (frame) dispatch(frame)
        }
      } catch (err) {
        if ((err as Error)?.name === 'AbortError') {
          // Cancelación intencional: no marcamos error.
        } else {
          patchMessage(assistantId, (m) => ({
            ...m,
            error:
              'El asistente no está disponible en este momento. Intenta de nuevo.',
            thinking: undefined,
          }))
        }
      } finally {
        finalize()
      }
    },
    [dispatch, finalize, patchMessage, sessionId],
  )

  const stop = useCallback(() => {
    abortRef.current?.abort()
    finalize()
  }, [finalize])

  const reset = useCallback(() => {
    abortRef.current?.abort()
    if (rafRef.current != null) {
      cancelAnimationFrame(rafRef.current)
      rafRef.current = null
    }
    pendingTokensRef.current = ''
    currentAssistantIdRef.current = null
    streamingRef.current = false
    setIsStreaming(false)
    setMessages([])
  }, [])

  // --- Gestión de conversaciones (multi-chat estilo ChatGPT) ---

  // Token monótono: descarta cargas viejas si el usuario cambia de chat rápido.
  const loadTokenRef = useRef(0)

  /** Carga en la vista los mensajes de una conversación (reemplaza los actuales). */
  const loadSession = useCallback((id: string, storageKey?: string) => {
    abortRef.current?.abort()
    const token = (loadTokenRef.current += 1)
    const tenant = effectiveTenantId()
    const key = storageKey ?? `${tenant}:${id}`
    setMessages([])
    fetch(`/api/assistant/history/${encodeURIComponent(key)}?limit=200`, {
      headers: authHeaders(),
    })
      .then((r) => (r.ok ? r.json() : []))
      .then((rows) => {
        if (token !== loadTokenRef.current) return
        const restored = mapHistoryRows(rows)
        setMessages(restored)
        // Si entramos a una conversación que aún no está en el índice (migrada
        // del modelo anterior o abierta desde auditoría), la registramos.
        if (restored.length > 0 && !hasChat(tenant, id)) {
          const firstUser = restored.find((m) => m.role === 'user')?.content
          touchChat(tenant, id, { title: firstUser })
          setChats(listChats(tenant))
        }
      })
      .catch(() => {
        if (token === loadTokenRef.current) setMessages([])
      })
  }, [])

  /** Abre una conversación en blanco (reutiliza la actual si ya está vacía). */
  const newChat = useCallback(() => {
    const tenant = effectiveTenantId()
    if (messages.length === 0 && !hasChat(tenant, sessionId)) return
    abortRef.current?.abort()
    const id = newChatId(tenant)
    setSessionId(id)
    setMessages([])
  }, [messages.length, sessionId])

  /** Cambia a otra conversación del dispositivo y carga sus mensajes. */
  const switchChat = useCallback(
    (id: string) => {
      if (id === sessionId) return
      setActiveChatId(effectiveTenantId(), id)
      setSessionId(id)
      loadSession(id)
    },
    [sessionId, loadSession],
  )

  /** Quita una conversación de la lista (el servidor conserva sus mensajes). */
  const removeChat = useCallback(
    (id: string) => {
      const tenant = effectiveTenantId()
      deleteChat(tenant, id)
      const remaining = listChats(tenant)
      setChats(remaining)
      if (id !== sessionId) return
      if (remaining.length > 0) {
        const next = remaining[0].id
        setActiveChatId(tenant, next)
        setSessionId(next)
        loadSession(next)
      } else {
        setSessionId(newChatId(tenant))
        setMessages([])
      }
    },
    [sessionId, loadSession],
  )

  /**
   * Entra a una conversación por su clave completa `<tenant>:<session_id>`
   * (auditoría de staff): abre en la vista principal, no en un lector aparte.
   */
  const enterSession = useCallback(
    (storageKey: string) => {
      const tenant = effectiveTenantId()
      const sep = storageKey.indexOf(':')
      const rawId = sep >= 0 ? storageKey.slice(sep + 1) : storageKey
      setActiveChatId(tenant, rawId)
      setSessionId(rawId)
      loadSession(rawId, storageKey)
    },
    [loadSession],
  )

  // Al montar y al cambiar de tenant: fija la conversación activa y carga sus
  // mensajes. Migra la sesión única del modelo anterior si existía.
  useEffect(() => {
    const tenant = effectiveTenantId()
    const active = getActiveChatId(tenant)
    setSessionId(active)
    setChats(listChats(tenant))
    loadSession(active)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- re-init al cambiar de tenant
  }, [teamId])

  // Aborta el stream en curso al desmontar.
  useEffect(() => {
    return () => {
      abortRef.current?.abort()
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current)
    }
  }, [])

  return {
    messages,
    isStreaming,
    sessionId,
    chats,
    sendMessage,
    stop,
    reset,
    newChat,
    switchChat,
    removeChat,
    enterSession,
  }
}
