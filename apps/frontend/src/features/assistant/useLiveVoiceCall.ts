import { useCallback, useEffect, useRef, useState } from 'react'
import { getAccessToken } from '../../lib/authFetch'

/**
 * Hook de la llamada en vivo (Deepgram STT/TTS sobre el MISMO agente RAG que
 * usa el chat SSE) contra el gateway WS de NestJS.
 *
 * Contrato completo: openspec/changes/live-call-deepgram/design.md
 * Un solo WebSocket a `/api/v1/live-call`: primer frame `{type:"auth"}` con
 * el JWT, después audio binario (mic PCM16/16kHz de subida, TTS PCM16/24kHz
 * de bajada) + frames JSON de control/eventos — mismo vocabulario que
 * `useAssistantChat.ts` (thinking/token/tool_start/tool_result/...) más los
 * eventos propios de voz (transcript_partial/final, turn_end,
 * assistant_speaking_start/end, barge_in, call_status).
 */

export type LiveCallStatus = 'idle' | 'connecting' | 'active' | 'ended' | 'error'

export type CallCard = {
  icon: string
  label: string
  value: string
  hint?: string
  tone?: 'amber'
}

export type Caption = {
  speaker: 'user' | 'ai'
  text: string
}

const TOOL_ICONS: Record<string, string> = {
  cotizar: 'request_quote',
  generar_documento: 'description',
  buscar_productos: 'search',
  capturar_datos_cliente: 'badge',
  registrar_consentimiento: 'verified_user',
  evaluar_riesgo: 'shield',
  emitir_poliza: 'task_alt',
  generar_link_pago: 'payments',
  verificar_pago: 'payments',
  solicitar_aclaracion: 'help',
  reportar_siniestro: 'report',
  estado_siniestro: 'report',
  documentos_siniestro: 'folder_open',
  proponer_renovacion: 'autorenew',
  actualizar_lead: 'person',
  listar_leads: 'groups',
  obtener_insights: 'insights',
}

const AMBER_TOOLS = new Set(['emitir_poliza', 'generar_link_pago'])

/** Traduce un `tool_result` genérico a una card presentable. Sin datos
 * estructurados por herramienta en el contrato SSE actual (solo `summary`
 * humano + `meta` terso) — esta es una versión genérica y honesta, no las
 * cards curadas a mano del guion de demo original. */
function toolResultToCard(tool: string, summary: string): CallCard {
  const label = tool.replaceAll('_', ' ').replace(/^./, (c) => c.toUpperCase())
  return {
    icon: TOOL_ICONS[tool] ?? 'auto_awesome',
    label,
    value: summary || 'Listo',
    tone: AMBER_TOOLS.has(tool) ? 'amber' : undefined,
  }
}

function liveCallWsUrl(): string {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${window.location.host}/api/v1/live-call`
}

type JsonFrame = { type: string; data?: Record<string, unknown> }

export function useLiveVoiceCall() {
  const [status, setStatus] = useState<LiveCallStatus>('idle')
  const [muted, setMuted] = useState(false)
  const [aiSpeaking, setAiSpeaking] = useState(false)
  const [caption, setCaption] = useState<Caption | null>(null)
  const [cards, setCards] = useState<CallCard[]>([])
  const [error, setError] = useState<string | null>(null)

  const wsRef = useRef<WebSocket | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const captureCtxRef = useRef<AudioContext | null>(null)
  const playbackCtxRef = useRef<AudioContext | null>(null)
  const playerNodeRef = useRef<AudioWorkletNode | null>(null)
  const mutedRef = useRef(false)
  const authedRef = useRef(false)
  const aiTextBufferRef = useRef('')

  const cleanup = useCallback(() => {
    authedRef.current = false
    wsRef.current?.close()
    wsRef.current = null
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    void captureCtxRef.current?.close()
    captureCtxRef.current = null
    void playbackCtxRef.current?.close()
    playbackCtxRef.current = null
    playerNodeRef.current = null
  }, [])

  const handleJson = useCallback((frame: JsonFrame) => {
    const data = frame.data ?? {}
    switch (frame.type) {
      case 'auth_ok':
        authedRef.current = true
        setStatus('active')
        break
      case 'auth_error':
      case 'error':
        setError(String(data.reason ?? data.message ?? 'Error en la llamada'))
        setStatus('error')
        break
      case 'transcript_partial':
        setCaption({ speaker: 'user', text: String(data.text ?? '') })
        break
      case 'transcript_final':
        setCards([]) // nuevo turno: las cards del turno anterior se desvanecen
        setCaption({ speaker: 'user', text: String(data.text ?? '') })
        break
      case 'thinking':
        aiTextBufferRef.current = ''
        setCaption({ speaker: 'ai', text: String(data.text ?? 'Pensando...') })
        break
      case 'token': {
        const chunk = String(data.text ?? '')
        if (!chunk) break
        aiTextBufferRef.current += chunk
        setCaption({ speaker: 'ai', text: aiTextBufferRef.current })
        break
      }
      case 'tool_result': {
        const tool = String(data.tool ?? '')
        if (!tool) break
        const summary = String(data.summary ?? '')
        setCards((prev) => [...prev, toolResultToCard(tool, summary)])
        break
      }
      case 'turn_end': {
        const replyText = String(data.reply_text ?? aiTextBufferRef.current)
        if (replyText) setCaption({ speaker: 'ai', text: replyText })
        break
      }
      case 'assistant_speaking_start':
        setAiSpeaking(true)
        break
      case 'assistant_speaking_end':
        setAiSpeaking(false)
        break
      case 'barge_in':
        setAiSpeaking(false)
        playerNodeRef.current?.port.postMessage({ cmd: 'clear' })
        break
      case 'call_status':
        setStatus('ended')
        break
      default:
        break
    }
  }, [])

  const startPlayback = useCallback(async (): Promise<void> => {
    const ctx = new AudioContext({ sampleRate: 24000 })
    await ctx.audioWorklet.addModule('/audio/pcm-player-processor.js')
    const player = new AudioWorkletNode(ctx, 'pcm-player-processor', {
      outputChannelCount: [1],
    })
    player.connect(ctx.destination)
    playbackCtxRef.current = ctx
    playerNodeRef.current = player
  }, [])

  const startCapture = useCallback(async (ws: WebSocket): Promise<void> => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    streamRef.current = stream
    const ctx = new AudioContext({ sampleRate: 16000 })
    await ctx.audioWorklet.addModule('/audio/mic-processor.js')
    const source = ctx.createMediaStreamSource(stream)
    const mic = new AudioWorkletNode(ctx, 'mic-processor')
    // Nodo de ganancia en 0: mantiene el worklet "tironeado" por el grafo de
    // audio sin reproducir el mic en los parlantes (evitaría feedback).
    const silence = ctx.createGain()
    silence.gain.value = 0
    source.connect(mic).connect(silence).connect(ctx.destination)
    mic.port.onmessage = (event: MessageEvent) => {
      if (authedRef.current && !mutedRef.current && ws.readyState === WebSocket.OPEN) {
        ws.send(event.data as ArrayBuffer)
      }
    }
    captureCtxRef.current = ctx
  }, [])

  const start = useCallback(async (): Promise<void> => {
    if (wsRef.current) return
    setStatus('connecting')
    setError(null)
    try {
      const token = getAccessToken()
      if (!token) throw new Error('No hay sesión activa')

      await startPlayback()

      const ws = new WebSocket(liveCallWsUrl())
      ws.binaryType = 'arraybuffer'
      wsRef.current = ws

      ws.onopen = () => {
        ws.send(JSON.stringify({ type: 'auth', data: { token } }))
      }
      ws.onmessage = (event: MessageEvent) => {
        if (typeof event.data === 'string') {
          try {
            handleJson(JSON.parse(event.data) as JsonFrame)
          } catch {
            // frame de texto no-JSON: se ignora
          }
        } else {
          const buffer = event.data as ArrayBuffer
          playerNodeRef.current?.port.postMessage(buffer, [buffer])
        }
      }
      ws.onerror = () => {
        setError('No se pudo conectar con la llamada en vivo')
        setStatus('error')
      }
      ws.onclose = () => {
        setStatus((s) => (s === 'error' ? s : 'ended'))
      }

      await startCapture(ws)
    } catch (err) {
      setError((err as Error)?.message ?? 'No se pudo iniciar la llamada')
      setStatus('error')
      cleanup()
    }
  }, [cleanup, handleJson, startCapture, startPlayback])

  const toggleMute = useCallback(() => {
    setMuted((prev) => {
      const next = !prev
      mutedRef.current = next
      wsRef.current?.send(JSON.stringify({ type: next ? 'mute' : 'unmute', data: {} }))
      return next
    })
  }, [])

  const endCall = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'end_call', data: {} }))
    }
    setStatus('ended')
    cleanup()
  }, [cleanup])

  useEffect(() => cleanup, [cleanup])

  return { status, muted, aiSpeaking, caption, cards, error, start, toggleMute, endCall }
}
