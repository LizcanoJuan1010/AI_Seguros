import { useEffect, useRef, useState } from 'react'
import { Icon } from '../../components/ui/Icon'
import { Button } from '../../components/ui/Button'
import { MessageMarkdown } from './MessageMarkdown'
import {
  CheckoutStepper,
  ClaimCard,
  PaymentCard,
  PolicyCard,
  UnderwritingCard,
} from './PolicyCard'
import { useAssistantChat } from './useAssistantChat'
import { ChatHistoryPanel } from './ChatHistoryPanel'
import { authHeaders } from '../../lib/authFetch'
import { downloadFile } from '../../lib/download'

/** Tipos de documento aceptados en el chat (extractores del servicio IA). */
const UPLOAD_ACCEPT =
  '.pdf,.doc,.docx,.xls,.xlsx,.pptx,.txt,.csv,.md,.json,.png,.jpg,.jpeg,.webp'
const MAX_UPLOAD_MB = 10

/**
 * Adjunto en preparación (estilo Gemini/GPT): el archivo se sube al soltarlo,
 * pero NO se envía al asistente hasta que el usuario mande el mensaje —
 * puede acumular varios y escribir sobre ellos.
 */
type StagedDoc = {
  key: string
  name: string
  status: 'uploading' | 'ready' | 'error'
  fileId?: string
  tipo?: string
}

function docIcon(name: string): string {
  const ext = name.split('.').pop()?.toLowerCase() ?? ''
  if (ext === 'pdf') return 'picture_as_pdf'
  if (['png', 'jpg', 'jpeg', 'webp', 'gif'].includes(ext)) return 'image'
  if (['xls', 'xlsx', 'csv'].includes(ext)) return 'table_chart'
  if (['ppt', 'pptx'].includes(ext)) return 'co_present'
  return 'description'
}

/** Bloque de adjuntos que viaja al final del mensaje (el agente lee los file_id). */
const ATTACH_BLOCK_RE = /\n*\[Documentos adjuntos: ([\s\S]*?)\]\s*$/

/**
 * Dictado por voz con la Web Speech API del navegador (Chrome/Edge). El TTS de
 * la respuesta va por `/api/assistant/tts` (Kokoro local, perfil `voz`); si el
 * perfil está apagado el toggle simplemente no suena — nunca rompe el chat.
 */
type SpeechRecognitionLike = {
  lang: string
  continuous: boolean
  interimResults: boolean
  start(): void
  stop(): void
  onresult:
    | ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void)
    | null
  onend: (() => void) | null
  onerror: (() => void) | null
}

const SpeechRecognitionCtor =
  typeof window !== 'undefined'
    ? (
        window as unknown as {
          SpeechRecognition?: new () => SpeechRecognitionLike
          webkitSpeechRecognition?: new () => SpeechRecognitionLike
        }
      ).SpeechRecognition ??
      (
        window as unknown as {
          webkitSpeechRecognition?: new () => SpeechRecognitionLike
        }
      ).webkitSpeechRecognition
    : undefined

function buildAttachBlock(docs: StagedDoc[]): string {
  const list = docs
    .map(
      (d) =>
        `"${d.name}" (file_id: ${d.fileId}${
          d.tipo && d.tipo !== 'desconocido' ? `, parece ${d.tipo.replaceAll('_', ' ')}` : ''
        })`,
    )
    .join(', ')
  return `\n\n[Documentos adjuntos: ${list}. Léelos con analizar_documento.]`
}
import type {
  AssistantDocument,
  ChatMessage,
  ToolCall,
} from './useAssistantChat'

const INITIAL_QUICK_REPLIES = [
  'Seguro de vida',
  'Proteger a mi familia',
  'Seguro de auto',
  'Voy a viajar',
]

const TOOL_LABELS: Record<string, string> = {
  cotizar: 'Cotización',
  cotizacion: 'Cotización',
  buscar_producto: 'Buscando producto',
  buscar_productos: 'Catálogo',
  catalogo: 'Catálogo',
  productos: 'Catálogo',
  generar_pdf: 'Generando PDF',
  documento: 'Documento',
  insights: 'Insights',
  generar_link_pago: 'Link de pago',
  verificar_pago: 'Verificando pago',
  solicitar_aclaracion: 'Aclaración de pago',
}

function toolLabel(tool: string, status: ToolCall['status']): string {
  const base =
    TOOL_LABELS[tool] ??
    tool.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())
  if (status === 'running') return `${base}…`
  return base
}

function ThinkingDots({ text }: { text?: string }) {
  return (
    <div className="flex items-center gap-2 py-1">
      <div className="flex items-center gap-1">
        <span className="size-2 animate-bounce rounded-full bg-primary [animation-delay:0ms]" />
        <span className="size-2 animate-bounce rounded-full bg-primary [animation-delay:150ms]" />
        <span className="size-2 animate-bounce rounded-full bg-primary [animation-delay:300ms]" />
      </div>
      {text ? (
        <span className="text-label-sm text-on-surface-variant">{text}</span>
      ) : null}
    </div>
  )
}

function ToolChip({ tool }: { tool: ToolCall }) {
  const running = tool.status === 'running'
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-label-sm font-semibold ${
        running
          ? 'border-amber-cta/40 bg-amber-cta/15 text-on-secondary-fixed-variant'
          : 'border-primary/20 bg-primary-fixed text-primary'
      }`}
    >
      {running ? (
        <Icon
          name="progress_activity"
          className="animate-spin text-[15px] text-primary"
        />
      ) : (
        <Icon name="check_circle" filled className="text-[15px] text-primary" />
      )}
      <span>{toolLabel(tool.tool, tool.status)}</span>
      {tool.status === 'done' && tool.summary ? (
        <span className="font-normal text-on-surface-variant">
          · {tool.summary}
        </span>
      ) : null}
    </span>
  )
}

function DocumentChip({ doc }: { doc: AssistantDocument }) {
  return (
    <Button
      variant="cta"
      className="rounded-full"
      onClick={() => downloadFile(doc.download_url)}
    >
      <Icon name="download" className="text-[18px]" />
      {doc.title}
    </Button>
  )
}

function QuickReplyChip({
  label,
  onClick,
  disabled,
}: {
  label: string
  onClick: () => void
  disabled?: boolean
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="inline-flex items-center gap-1.5 rounded-full border border-amber-cta/50 bg-amber-cta/15 px-3.5 py-1.5 text-label-sm font-semibold text-on-secondary-fixed-variant transition-all hover:border-amber-cta hover:bg-amber-cta/25 disabled:cursor-not-allowed disabled:opacity-50"
    >
      <Icon name="bolt" filled className="text-[15px] text-secondary" />
      {label}
    </button>
  )
}

function AssistantBubble({
  message,
  isStreaming,
  onQuickReply,
}: {
  message: ChatMessage
  isStreaming: boolean
  onQuickReply: (text: string) => void
}) {
  const showCursor = !message.done && message.content.length > 0
  const showThinking =
    !message.done && !message.content && !message.error && !!message.thinking

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-start gap-3">
        <div className="flex size-8 flex-shrink-0 items-center justify-center rounded-full bg-primary text-white shadow-sm">
          <Icon name="psychology" className="text-[18px]" />
        </div>
        <div className="min-w-0 max-w-[85%] rounded-2xl rounded-tl-none border border-outline-variant/30 bg-white p-4 shadow-sm">
          {message.tools.length > 0 ? (
            <div className="mb-2 flex flex-wrap gap-2">
              {message.tools.map((tool) => (
                <ToolChip key={tool.id} tool={tool} />
              ))}
            </div>
          ) : null}

          {message.error ? (
            <div className="flex items-start gap-2 text-body-md text-on-error-container">
              <Icon
                name="error"
                filled
                className="mt-0.5 text-[18px] text-error"
              />
              <span>{message.error}</span>
            </div>
          ) : message.content ? (
            <div className="min-w-0">
              <MessageMarkdown content={message.content} />
              {showCursor ? <span className="typing-cursor" /> : null}
            </div>
          ) : showThinking ? (
            <ThinkingDots text={message.thinking} />
          ) : (
            <ThinkingDots />
          )}

          {message.documents.length > 0 ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {message.documents.map((doc) => (
                <DocumentChip key={doc.download_url} doc={doc} />
              ))}
            </div>
          ) : null}

          {message.checkout && !message.policy ? (
            <CheckoutStepper current={message.checkout.step} />
          ) : null}

          {message.underwriting ? (
            <UnderwritingCard underwriting={message.underwriting} />
          ) : null}

          {message.payment ? <PaymentCard payment={message.payment} /> : null}

          {message.claim ? <ClaimCard claim={message.claim} /> : null}
        </div>
      </div>

      {message.policy ? (
        <div className="ml-11 max-w-[85%]">
          <PolicyCard policy={message.policy} />
        </div>
      ) : null}

      {message.quickReplies.length > 0 ? (
        <div className="ml-11 flex flex-wrap gap-2">
          {message.quickReplies.map((qr) => (
            <QuickReplyChip
              key={qr}
              label={qr}
              disabled={isStreaming}
              onClick={() => onQuickReply(qr)}
            />
          ))}
        </div>
      ) : null}
    </div>
  )
}

function UserBubble({ message }: { message: ChatMessage }) {
  // El bloque técnico de adjuntos se muestra como chips, no como texto crudo.
  const match = message.content.match(ATTACH_BLOCK_RE)
  const text = match
    ? message.content.replace(ATTACH_BLOCK_RE, '').trim()
    : message.content
  const attachedNames = match
    ? Array.from(match[1].matchAll(/"([^"]+)"/g), (m) => m[1])
    : []

  return (
    <div className="flex items-start justify-end gap-3">
      <div className="max-w-[85%] rounded-2xl rounded-tr-none bg-primary-container p-4 text-white shadow-md">
        {text && <p className="whitespace-pre-wrap text-body-md">{text}</p>}
        {attachedNames.length > 0 && (
          <div className={`flex flex-wrap gap-2 ${text ? 'mt-3' : ''}`}>
            {attachedNames.map((name) => (
              <span
                key={name}
                className="flex items-center gap-1.5 rounded-lg bg-white/15 px-2.5 py-1.5 text-label-sm"
              >
                <Icon name={docIcon(name)} className="text-[16px]" />
                <span className="max-w-44 truncate">{name}</span>
              </span>
            ))}
          </div>
        )}
      </div>
      <div className="flex size-8 flex-shrink-0 items-center justify-center rounded-full bg-surface-variant text-on-surface">
        <Icon name="person" className="text-[18px]" />
      </div>
    </div>
  )
}

function EmptyState({
  onQuickReply,
  disabled,
}: {
  onQuickReply: (text: string) => void
  disabled: boolean
}) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-stack-lg px-4 text-center">
      <div className="ai-glow flex size-20 items-center justify-center rounded-full bg-primary text-white">
        <Icon name="psychology" className="text-[40px]" />
      </div>
      <div className="space-y-2">
        <h2 className="text-headline-md text-forest-deep">
          Hola, soy tu asesor Tequendama
        </h2>
        <p className="mx-auto max-w-md text-body-md text-on-surface-variant">
          Te ayudo a encontrar el seguro ideal, cotizar en segundos y generar tu
          propuesta en PDF. ¿Con qué empezamos?
        </p>
      </div>
      <div className="flex flex-wrap items-center justify-center gap-2">
        {INITIAL_QUICK_REPLIES.map((qr) => (
          <QuickReplyChip
            key={qr}
            label={qr}
            disabled={disabled}
            onClick={() => onQuickReply(qr)}
          />
        ))}
      </div>
    </div>
  )
}

export function AssistantChat() {
  const { messages, isStreaming, sendMessage, sessionId } = useAssistantChat()
  const [input, setInput] = useState('')
  const [attachments, setAttachments] = useState<StagedDoc[]>([])
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [listening, setListening] = useState(false)
  const [voiceOn, setVoiceOn] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const recogRef = useRef<SpeechRecognitionLike | null>(null)
  const spokenRef = useRef<Set<string>>(new Set())
  const audioRef = useRef<HTMLAudioElement | null>(null)

  /** Dictado: un toque escucha, otro detiene. El texto cae al input editable. */
  const toggleMic = () => {
    if (listening) {
      recogRef.current?.stop()
      return
    }
    if (!SpeechRecognitionCtor) return
    const rec = new SpeechRecognitionCtor()
    rec.lang = 'es-CO'
    rec.continuous = false
    rec.interimResults = true
    rec.onresult = (e) => {
      const transcript = Array.from(
        { length: e.results.length },
        (_, i) => e.results[i][0]?.transcript ?? '',
      ).join(' ')
      setInput(transcript)
    }
    rec.onend = () => setListening(false)
    rec.onerror = () => setListening(false)
    recogRef.current = rec
    setListening(true)
    rec.start()
  }

  // Respuesta hablada: al terminar un mensaje del asistente, se sintetiza una
  // sola vez (Set de ids ya hablados). Si el TTS no está disponible, silencio.
  useEffect(() => {
    if (!voiceOn) return
    const last = [...messages]
      .reverse()
      .find((m) => m.role === 'assistant' && m.done && m.content && !m.error)
    if (!last || spokenRef.current.has(last.id)) return
    spokenRef.current.add(last.id)
    fetch(`/api/assistant/tts?text=${encodeURIComponent(last.content.slice(0, 500))}`)
      .then((r) => (r.ok ? r.blob() : Promise.reject(new Error('tts'))))
      .then((blob) => {
        audioRef.current?.pause()
        const audio = new Audio(URL.createObjectURL(blob))
        audioRef.current = audio
        void audio.play()
      })
      .catch(() => {
        /* perfil voz apagado: el chat sigue en texto */
      })
  }, [messages, voiceOn])

  /**
   * Adjuntar (estilo Gemini/GPT): cada archivo se sube de inmediato en
   * segundo plano y queda como chip "listo" en el composer. NO se envía nada
   * al asistente hasta que el usuario oprima Enter/enviar — puede acumular
   * varios documentos y escribir un mensaje sobre ellos.
   */
  const handleFiles = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? [])
    e.target.value = ''
    if (!files.length) return
    setUploadError(null)

    for (const file of files) {
      if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
        setUploadError(`"${file.name}" supera ${MAX_UPLOAD_MB} MB.`)
        continue
      }
      const key = `${file.name}-${file.size}-${Math.random().toString(36).slice(2, 8)}`
      setAttachments((prev) => [
        ...prev,
        { key, name: file.name, status: 'uploading' },
      ])
      const form = new FormData()
      form.append('file', file)
      fetch(`/api/assistant/upload?session_id=${encodeURIComponent(sessionId)}`, {
        method: 'POST',
        headers: { ...authHeaders() },
        body: form,
      })
        .then(async (res) => {
          if (!res.ok) throw new Error(`HTTP ${res.status}`)
          const data = (await res.json()) as {
            file_id: string
            tipo_detectado?: string
          }
          setAttachments((prev) =>
            prev.map((a) =>
              a.key === key
                ? { ...a, status: 'ready', fileId: data.file_id, tipo: data.tipo_detectado }
                : a,
            ),
          )
        })
        .catch(() => {
          setAttachments((prev) =>
            prev.map((a) => (a.key === key ? { ...a, status: 'error' } : a)),
          )
        })
    }
  }

  const removeAttachment = (key: string) => {
    setAttachments((prev) => prev.filter((a) => a.key !== key))
  }

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const nearBottom =
      el.scrollHeight - el.scrollTop - el.clientHeight < 160
    if (nearBottom) {
      el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
    }
  }, [messages])

  const resetTextareaHeight = () => {
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
  }

  const submit = (text?: string) => {
    const value = (text ?? input).trim()
    const ready = attachments.filter((a) => a.status === 'ready')
    const stillUploading = attachments.some((a) => a.status === 'uploading')
    // Enviar requiere texto o al menos un adjunto listo (y ninguno subiendo).
    if ((!value && ready.length === 0) || isStreaming || stillUploading) return
    let message = value
    if (ready.length > 0) {
      message =
        (value || 'Te adjunté estos documentos, revísalos por favor.') +
        buildAttachBlock(ready)
    }
    void sendMessage(message)
    setInput('')
    setAttachments([])
    setUploadError(null)
    resetTextareaHeight()
  }

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const el = e.currentTarget
    setInput(el.value)
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  const readyCount = attachments.filter((a) => a.status === 'ready').length
  const anyUploading = attachments.some((a) => a.status === 'uploading')
  const canSend =
    (input.trim().length > 0 || readyCount > 0) && !isStreaming && !anyUploading

  return (
    <div className="flex h-full min-h-0 flex-col bg-surface">
      {/* Header */}
      <header className="glass-header sticky top-0 z-10 flex items-center gap-3 border-b border-outline-variant px-4 py-3 md:px-6">
        <div className="flex size-10 items-center justify-center rounded-full bg-primary text-white shadow-sm">
          <Icon name="psychology" className="text-[22px]" />
        </div>
        <div className="min-w-0">
          <p className="text-label-md font-bold text-on-surface">
            Asistente Tequendama
          </p>
          <p className="flex items-center gap-1.5 text-label-sm text-on-surface-variant">
            <span
              className={`size-2 rounded-full ${
                isStreaming ? 'animate-pulse bg-amber-cta' : 'bg-primary'
              }`}
            />
            {isStreaming ? 'Escribiendo…' : 'En línea · IA de seguros'}
          </p>
        </div>
        <button
          type="button"
          onClick={() => setVoiceOn((v) => !v)}
          aria-label={voiceOn ? 'Silenciar respuestas' : 'Escuchar respuestas'}
          title={
            voiceOn
              ? 'Respuestas con voz activadas'
              : 'Escuchar las respuestas en voz alta'
          }
          className={`ml-auto flex size-10 items-center justify-center rounded-full transition-colors hover:bg-surface-variant ${
            voiceOn ? 'text-primary' : 'text-on-surface-variant hover:text-primary'
          }`}
        >
          <Icon name={voiceOn ? 'volume_up' : 'volume_off'} className="text-[22px]" />
        </button>
        <button
          type="button"
          onClick={() => setHistoryOpen(true)}
          aria-label="Ver historial de conversaciones"
          title="Historial de conversaciones"
          className="flex size-10 items-center justify-center rounded-full text-on-surface-variant transition-colors hover:bg-surface-variant hover:text-primary"
        >
          <Icon name="history" className="text-[22px]" />
        </button>
      </header>

      <ChatHistoryPanel
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        currentSessionId={sessionId}
      />

      {/* Mensajes */}
      <div
        ref={scrollRef}
        className="min-h-0 flex-1 overflow-y-auto px-4 py-6 md:px-6"
      >
        {messages.length === 0 ? (
          <EmptyState onQuickReply={submit} disabled={isStreaming} />
        ) : (
          <div className="mx-auto flex max-w-3xl flex-col gap-stack-lg">
            {messages.map((message) =>
              message.role === 'assistant' ? (
                <AssistantBubble
                  key={message.id}
                  message={message}
                  isStreaming={isStreaming}
                  onQuickReply={submit}
                />
              ) : (
                <UserBubble key={message.id} message={message} />
              ),
            )}
          </div>
        )}
      </div>

      {/* Input */}
      <div className="border-t border-outline-variant bg-surface-container-lowest px-4 py-3 md:px-6">
        {/* Adjuntos en preparación (chips, estilo Gemini/GPT) */}
        {attachments.length > 0 && (
          <div className="mx-auto mb-2 flex max-w-3xl flex-wrap gap-2">
            {attachments.map((a) => (
              <span
                key={a.key}
                className={`flex items-center gap-2 rounded-xl border px-3 py-1.5 text-label-sm shadow-sm ${
                  a.status === 'error'
                    ? 'border-error/50 bg-error-container/40 text-on-error-container'
                    : 'border-outline-variant bg-white text-on-surface'
                }`}
              >
                <Icon
                  name={
                    a.status === 'uploading' ? 'progress_activity' : docIcon(a.name)
                  }
                  className={`text-[16px] ${
                    a.status === 'uploading'
                      ? 'animate-spin text-outline'
                      : a.status === 'error'
                        ? 'text-error'
                        : 'text-primary'
                  }`}
                />
                <span className="max-w-44 truncate">{a.name}</span>
                {a.status === 'ready' && a.tipo && a.tipo !== 'desconocido' && (
                  <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] uppercase text-primary">
                    {a.tipo.replaceAll('_', ' ')}
                  </span>
                )}
                {a.status === 'error' && <span>falló</span>}
                <button
                  type="button"
                  onClick={() => removeAttachment(a.key)}
                  aria-label={`Quitar ${a.name}`}
                  className="text-outline transition-colors hover:text-error"
                >
                  <Icon name="close" className="text-[16px]" />
                </button>
              </span>
            ))}
          </div>
        )}
        <div className="mx-auto flex max-w-3xl items-end gap-2">
          <input
            ref={fileRef}
            type="file"
            multiple
            accept={UPLOAD_ACCEPT}
            className="hidden"
            onChange={handleFiles}
          />
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            disabled={isStreaming}
            aria-label="Adjuntar documentos"
            title="Adjuntar documentos (PDF, Word, Excel, imagen... puedes elegir varios)"
            className="flex size-11 flex-shrink-0 items-center justify-center rounded-full border border-outline-variant bg-white text-on-surface-variant shadow-sm transition-all hover:border-primary hover:text-primary active:scale-95 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Icon name="attach_file" className="text-[20px]" />
          </button>
          {SpeechRecognitionCtor ? (
            <button
              type="button"
              onClick={toggleMic}
              disabled={isStreaming}
              aria-label={listening ? 'Detener dictado' : 'Dictar por voz'}
              title={listening ? 'Escuchando… toca para detener' : 'Dictar por voz'}
              className={`flex size-11 flex-shrink-0 items-center justify-center rounded-full border shadow-sm transition-all active:scale-95 disabled:cursor-not-allowed disabled:opacity-40 ${
                listening
                  ? 'animate-pulse border-error bg-error text-on-error'
                  : 'border-outline-variant bg-white text-on-surface-variant hover:border-primary hover:text-primary'
              }`}
            >
              <Icon name={listening ? 'stop' : 'mic'} filled={listening} className="text-[20px]" />
            </button>
          ) : null}
          <div className="flex flex-1 items-end rounded-2xl border border-outline-variant bg-white px-3 py-2 shadow-sm transition-colors focus-within:border-primary">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={handleInput}
              onKeyDown={handleKeyDown}
              rows={1}
              placeholder="Escribe tu mensaje…"
              className="max-h-40 flex-1 resize-none bg-transparent text-body-md text-on-surface outline-none placeholder:text-outline"
            />
          </div>
          <button
            type="button"
            onClick={() => submit()}
            disabled={!canSend}
            aria-label="Enviar mensaje"
            className="flex size-11 flex-shrink-0 items-center justify-center rounded-full bg-primary text-white shadow-sm transition-all hover:opacity-90 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Icon name="send" filled className="text-[20px]" />
          </button>
        </div>
        <p className="mx-auto mt-1.5 max-w-3xl text-center text-label-sm text-outline">
          {uploadError ? (
            <span className="text-error">{uploadError}</span>
          ) : anyUploading ? (
            'Subiendo documentos…'
          ) : readyCount > 0 ? (
            `${readyCount} documento${readyCount > 1 ? 's' : ''} listo${readyCount > 1 ? 's' : ''} — escribe algo sobre ellos o presiona Enter para enviarlos`
          ) : (
            <>
              Enter envía · Shift+Enter salto de línea · 📎 adjunta uno o varios
              documentos (PDF, Word, Excel, imagen) y escribe sobre ellos
            </>
          )}
        </p>
      </div>
    </div>
  )
}
