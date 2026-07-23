import { useEffect, useRef, useState } from 'react'
import { Icon } from '../../components/ui/Icon'
import { Button } from '../../components/ui/Button'
import { MessageMarkdown } from './MessageMarkdown'
import { CheckoutStepper, PolicyCard } from './PolicyCard'
import { useAssistantChat } from './useAssistantChat'
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
      onClick={() => window.open(doc.download_url, '_blank', 'noopener')}
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
  return (
    <div className="flex items-start justify-end gap-3">
      <div className="max-w-[85%] rounded-2xl rounded-tr-none bg-primary-container p-4 text-white shadow-md">
        <p className="whitespace-pre-wrap text-body-md">{message.content}</p>
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
  const { messages, isStreaming, sendMessage } = useAssistantChat()
  const [input, setInput] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

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
    if (!value || isStreaming) return
    void sendMessage(value)
    setInput('')
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

  const canSend = input.trim().length > 0 && !isStreaming

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
      </header>

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
        <div className="mx-auto flex max-w-3xl items-end gap-2">
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
          Enter envía · Shift+Enter salto de línea
        </p>
      </div>
    </div>
  )
}
