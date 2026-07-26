import { useCallback, useEffect, useRef, useState } from 'react'
import { getAccessToken } from '../../lib/authFetch'
import { getDeviceId } from '../../lib/clientIdentity'
import type { AssistantPayment, PaymentStatus } from './useAssistantChat'

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
  /** Pago en curso (evento `payment_link`); CTA en pantalla, no TTS de la URL. */
  const [payment, setPayment] = useState<AssistantPayment | null>(null)
  const [error, setError] = useState<string | null>(null)

  const wsRef = useRef<WebSocket | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const captureCtxRef = useRef<AudioContext | null>(null)
  const playbackCtxRef = useRef<AudioContext | null>(null)
  const playerNodeRef = useRef<AudioWorkletNode | null>(null)
  const mutedRef = useRef(false)
  const authedRef = useRef(false)
  const aiTextBufferRef = useRef('')
  const resumeListenerRef = useRef<(() => void) | null>(null)
  /** Candado síncrono + generación: StrictMode remonta el efecto y `start`
   * es async — sin esto se abrían dos WS Nest→Python en paralelo. */
  const startingRef = useRef(false)
  const startGenRef = useRef(0)
  /** Tras barge_in, ignora PCM residual hasta el próximo assistant_speaking_start. */
  const dropAudioUntilSpeakStartRef = useRef(false)

  /** Reintenta resume() en los AudioContext que sigan suspendidos. Se usa
   * como fallback ante navegadores que no cuentan el montaje de la página
   * (useEffect) como gesto de usuario válido para autoplay — el primer
   * click/tap en cualquier parte de la pantalla los despierta. */
  const resumeSuspendedContexts = useCallback(() => {
    if (captureCtxRef.current?.state === 'suspended') {
      void captureCtxRef.current.resume()
    }
    if (playbackCtxRef.current?.state === 'suspended') {
      void playbackCtxRef.current.resume()
    }
  }, [])

  const cleanup = useCallback(() => {
    if (resumeListenerRef.current) {
      document.removeEventListener('pointerdown', resumeListenerRef.current)
      resumeListenerRef.current = null
    }
    // Invalida cualquier `start()` en vuelo (StrictMode / unmount).
    startGenRef.current += 1
    startingRef.current = false
    authedRef.current = false
    dropAudioUntilSpeakStartRef.current = false
    setPayment(null)
    // Estado de conversación limpio para el siguiente intento: sin esto,
    // "Volver a llamar" arrancaba MUDO si la llamada anterior murió
    // silenciada, con las cards viejas proyectadas y el orbe en "hablando".
    mutedRef.current = false
    setMuted(false)
    setCards([])
    setCaption(null)
    setAiSpeaking(false)
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
      // Frames del cierre que antes se DESCARTABAN en voz: el agente tiene
      // prohibido dictar URLs, así que sin esta card el link de descarga de
      // la póliza se perdía del todo, y un REFER/DECLINE del underwriting no
      // se veía en pantalla.
      case 'policy': {
        const numero = String(data.policyNumber ?? '').trim()
        if (!numero) break
        setCards((prev) => [
          ...prev,
          {
            icon: 'verified',
            label: 'Póliza emitida',
            value: numero,
            hint:
              typeof data.download_url === 'string' && data.download_url
                ? 'Tu póliza quedó activa — descárgala desde el chat al colgar'
                : 'Tu póliza quedó activa',
            tone: 'amber',
          },
        ])
        break
      }
      case 'underwriting': {
        const decision = String(data.decision ?? '').toUpperCase()
        if (!decision) break
        setCards((prev) => [
          ...prev,
          {
            icon: decision === 'AUTO_APPROVE' ? 'task_alt' : 'schedule',
            label: 'Evaluación de riesgo',
            value:
              decision === 'AUTO_APPROVE'
                ? 'Aprobada automáticamente'
                : decision === 'REFER'
                  ? 'Un asesor la revisa (<24h)'
                  : 'No asegurable por este canal',
          },
        ])
        break
      }
      case 'payment_link': {
        const reference = String(data.reference ?? '').trim()
        if (!reference) break
        const checkoutUrl =
          typeof data.checkout_url === 'string' && data.checkout_url
            ? data.checkout_url
            : null
        const status = String(data.status ?? 'PENDING').toUpperCase() as PaymentStatus
        setPayment((prev) => {
          // Actualizaciones de verificar_pago pueden venir sin checkout_url:
          // conservar la URL previa del mismo reference.
          const keepUrl =
            checkoutUrl ??
            (prev?.reference === reference ? prev.checkout_url : null) ??
            null
          return {
            reference,
            checkout_url: keepUrl,
            amount_cop:
              typeof data.amount_cop === 'number' ? data.amount_cop : prev?.amount_cop,
            concept:
              typeof data.concept === 'string' ? data.concept : prev?.concept,
            status,
            provider:
              typeof data.provider === 'string' ? data.provider : prev?.provider,
            demo: Boolean(data.demo ?? prev?.demo),
          }
        })
        break
      }
      case 'turn_end': {
        const replyText = String(data.reply_text ?? aiTextBufferRef.current)
        if (replyText) setCaption({ speaker: 'ai', text: replyText })
        break
      }
      case 'assistant_speaking_start':
        dropAudioUntilSpeakStartRef.current = false
        setAiSpeaking(true)
        break
      case 'assistant_speaking_end':
        setAiSpeaking(false)
        break
      case 'barge_in':
        setAiSpeaking(false)
        dropAudioUntilSpeakStartRef.current = true
        playerNodeRef.current?.port.postMessage({ cmd: 'clear' })
        break
      case 'call_status':
        // FALLIDA (el motor de voz se cayó a mitad de llamada) no es un
        // colgado limpio: como 'ended' redirigía al chat en 1 s tapando lo
        // que pasó; como 'error' se queda con el mensaje y el reintento.
        if (String(data.status ?? '').toUpperCase() === 'FALLIDA') {
          setError('Se perdió la conexión con el servicio de voz')
          setStatus('error')
        } else {
          setStatus('ended')
        }
        break
      default:
        break
    }
  }, [])

  const startPlayback = useCallback(async (gen: number): Promise<void> => {
    const ctx = new AudioContext({ sampleRate: 24000 })
    // Sin gesto de usuario previo (entrar a /llamada por URL directa o F5),
    // la promesa de resume() queda PENDIENTE para siempre — esperarla colgaba
    // todo start() en "Conectando..." sin llegar siquiera a abrir el WS. No
    // se espera: el worklet carga igual en 'suspended' y el primer click
    // despierta el contexto (listener de pointerdown en start()).
    void ctx.resume()
    await ctx.audioWorklet.addModule('/audio/pcm-player-processor.js')
    // Si la llamada murió durante el await (cleanup corrió), cerrar ESTE
    // contexto en vez de repoblarlo en los refs: Chrome corta alrededor de
    // ~6 AudioContext por documento y los huérfanos se acumulaban por ciclo.
    if (gen !== startGenRef.current) {
      void ctx.close()
      throw new Error('llamada cancelada')
    }
    const player = new AudioWorkletNode(ctx, 'pcm-player-processor', {
      outputChannelCount: [1],
    })
    player.connect(ctx.destination)
    playbackCtxRef.current = ctx
    playerNodeRef.current = player
  }, [])

  const startCapture = useCallback(async (ws: WebSocket, gen: number): Promise<void> => {
    // AEC/NS explícitos: sin echoCancellation, la voz de la IA saliendo por
    // los parlantes vuelve a entrar por el mic y dispara barge_in en loop.
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
    })
    // El permiso pudo tardar (diálogo abierto) y la llamada morir mientras
    // tanto: si este start ya no es el vigente, soltar el mic INMEDIATAMENTE
    // — sin esto quedaba el punto rojo de grabación encendido sobre la
    // pantalla de error, con la página diciendo "no pudimos conectar".
    if (gen !== startGenRef.current) {
      stream.getTracks().forEach((t) => t.stop())
      throw new Error('llamada cancelada')
    }
    streamRef.current = stream
    const ctx = new AudioContext({ sampleRate: 16000 })
    void ctx.resume() // sin gesto previo quedaría pendiente — ver startPlayback
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
    // Guard síncrono ANTES de cualquier await — StrictMode en dev monta el
    // efecto dos veces y sin esto se abrían dos WS Nest→Python en paralelo.
    if (startingRef.current || wsRef.current) return
    startingRef.current = true
    const gen = ++startGenRef.current
    setStatus('connecting')
    setError(null)
    // El rescate de autoplay se registra ANTES de crear los AudioContext: el
    // primer click despierta lo que haya nacido 'suspended'. Registrarlo al
    // final (como antes) significaba que si algo se colgaba en el camino, el
    // listener nunca existía y la pantalla moría en "Conectando...".
    if (!resumeListenerRef.current) {
      const onFirstPointerDown = () => resumeSuspendedContexts()
      resumeListenerRef.current = onFirstPointerDown
      document.addEventListener('pointerdown', onFirstPointerDown, { once: true })
    }
    try {
      // Staff con sesión -> JWT. Cliente final -> device_id anónimo: la
      // landing enlaza /llamada directo y un lead no debería tener que
      // loguearse para hablar (ver live-call.gateway.ts, que valida el
      // formato y limita las llamadas simultáneas por dispositivo).
      const token = getAccessToken()
      const authFrame = token
        ? { token }
        : { device_id: getDeviceId() }

      await startPlayback(gen)
      if (gen !== startGenRef.current) return

      const ws = new WebSocket(liveCallWsUrl())
      ws.binaryType = 'arraybuffer'
      wsRef.current = ws

      ws.onopen = () => {
        if (gen !== startGenRef.current) {
          ws.close()
          return
        }
        ws.send(JSON.stringify({ type: 'auth', data: authFrame }))
      }
      ws.onmessage = (event: MessageEvent) => {
        if (typeof event.data === 'string') {
          try {
            handleJson(JSON.parse(event.data) as JsonFrame)
          } catch {
            // frame de texto no-JSON: se ignora
          }
        } else {
          if (dropAudioUntilSpeakStartRef.current) return
          const buffer = event.data as ArrayBuffer
          playerNodeRef.current?.port.postMessage(buffer, [buffer])
        }
      }
      ws.onerror = () => {
        if (gen !== startGenRef.current) return
        setError('No se pudo conectar con la llamada en vivo')
        setStatus('error')
      }
      ws.onclose = () => {
        if (gen !== startGenRef.current) return
        // Un cierre ANTES de auth_ok no es un colgado limpio: es el servidor
        // caído/reiniciado a mitad del handshake. Tratarlo como 'ended'
        // catapultaba al usuario al chat sin explicación (el redirect de
        // 1 s); como 'error' se queda con el mensaje y "Volver a llamar".
        // OJO: leer authedRef ANTES de cleanup(), que lo resetea.
        const huboLlamada = authedRef.current
        if (!huboLlamada) {
          setError('Se perdió la conexión antes de iniciar la llamada')
        }
        setStatus((s) => (s === 'error' ? s : huboLlamada ? 'ended' : 'error'))
        // Cierre iniciado por el SERVIDOR (error del servicio de voz, fin de
        // sesión): sin este cleanup, `wsRef` queda apuntando al socket muerto
        // y el guard de `start()` bloquea cualquier reintento — el botón
        // "Volver a llamar" no haría nada. (El cierre iniciado por nosotros
        // ya pasó por cleanup(), que invalida `gen` y no entra aquí.)
        cleanup()
      }

      await startCapture(ws, gen)
      if (gen !== startGenRef.current) {
        ws.close()
        return
      }

      resumeSuspendedContexts()

      // Watchdog del handshake: si en 15 s no llegó auth_ok (proxy que traga
      // el upgrade, backend que acepta TCP y no contesta) no había NINGUNA
      // salida — la pantalla moría en "Conectando…" sin botón de reintento.
      window.setTimeout(() => {
        if (gen !== startGenRef.current || authedRef.current) return
        setError('No pudimos conectar la llamada — revisa tu conexión')
        setStatus('error')
        cleanup()
      }, 15_000)
    } catch (err) {
      if (gen !== startGenRef.current) return
      const e = err as Error
      // El error crudo del navegador es críptico y en inglés ("Permission
      // denied"). Con el permiso BLOQUEADO además el prompt ya no reaparece:
      // reintentar rechaza al instante para siempre — hay que decirle dónde
      // desbloquearlo, no solo que falló.
      setError(
        e?.name === 'NotAllowedError' || e?.name === 'NotFoundError'
          ? 'Necesitamos permiso del micrófono para la llamada — habilítalo en el candado de la barra de direcciones y vuelve a intentar'
          : (e?.message ?? 'No se pudo iniciar la llamada'),
      )
      setStatus('error')
      cleanup()
    }
  }, [cleanup, handleJson, resumeSuspendedContexts, startCapture, startPlayback])

  const toggleMute = useCallback(() => {
    const next = !mutedRef.current
    mutedRef.current = next
    // Guard de OPEN obligatorio (igual que endCall): durante CONNECTING,
    // send() lanza InvalidStateError — y como antes vivía DENTRO del updater
    // de setMuted, la excepción salía en fase de render y desmontaba la app
    // entera en blanco. Un click a "Silenciar" mientras decía "Conectando…"
    // bastaba para tumbar todo.
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: next ? 'mute' : 'unmute', data: {} }))
    }
    setMuted(next)
  }, [])

  const endCall = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'end_call', data: {} }))
    }
    setStatus('ended')
    cleanup()
  }, [cleanup])

  useEffect(() => cleanup, [cleanup])

  return {
    status,
    muted,
    aiSpeaking,
    caption,
    cards,
    payment,
    error,
    start,
    toggleMute,
    endCall,
  }
}
