import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { getStoredTenantId } from '../../lib/api'
import { authHeaders } from '../../lib/authFetch'
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
 * quick_replies | document | checkout_step | policy | done | error.
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
  | { event: 'done'; data: { session_id?: string } }
  | { event: 'error'; data: { message?: string } }
  | { event: string; data: unknown }

const SESSION_KEY = 'teq_assistant_session_id'
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

function loadSessionId(): string {
  if (typeof window === 'undefined') return makeId('sess')
  // Sesión (y por tanto memoria del asistente) particionada por tenant:
  // cambiar de equipo abre una conversación independiente.
  const key = `${SESSION_KEY}_${effectiveTenantId()}`
  try {
    const existing = window.localStorage.getItem(key)
    if (existing) return existing
    const fresh = makeId('sess')
    window.localStorage.setItem(key, fresh)
    return fresh
  } catch {
    return makeId('sess')
  }
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

  const { teamId } = useTenant()
  // eslint-disable-next-line react-hooks/exhaustive-deps -- re-deriva la sesión al cambiar de tenant
  const sessionId = useMemo(loadSessionId, [teamId])

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

  // Aborta el stream en curso al desmontar.
  useEffect(() => {
    return () => {
      abortRef.current?.abort()
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current)
    }
  }, [])

  return { messages, isStreaming, sessionId, sendMessage, stop, reset }
}
