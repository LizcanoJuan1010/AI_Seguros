import { useEffect, useState, type CSSProperties } from 'react'
import { AiVisualizerStub, type AiOrbState } from '../features/call/AiVisualizerStub'
import { CallControls } from '../features/call/CallControls'
import { Icon } from '../components/ui/Icon'
import { PaymentCard } from '../features/assistant/PolicyCard'
import { useLiveVoiceCall, type CallCard } from '../features/assistant/useLiveVoiceCall'

function formatDuration(s: number): string {
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}

export function LiveAiCallPage() {
  const {
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
  } = useLiveVoiceCall()
  const [sentNote, setSentNote] = useState(false)
  const [seconds, setSeconds] = useState(0)
  const [displayCards, setDisplayCards] = useState<CallCard[] | null>(null)
  const [cardsLeaving, setCardsLeaving] = useState(false)

  const ended = status === 'ended' || status === 'error'
  const showingPayment = Boolean(payment?.reference)

  // Arranca la llamada al entrar. StrictMode en dev monta/desmonta el efecto
  // dos veces: el cleanup invalida el start en vuelo (startGenRef) y el
  // remount abre una sola conexión estable.
  useEffect(() => {
    void start()
    return () => {
      endCall()
    }
    // Solo al montar la pantalla — start/endCall son estables (useCallback).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Cronómetro real: solo corre mientras la llamada está activa de verdad.
  useEffect(() => {
    if (status !== 'active') return
    const id = window.setInterval(() => setSeconds((s) => s + 1), 1000)
    return () => window.clearInterval(id)
  }, [status])

  // Proyección de cards: entran cuando el turno trae tool_result y se
  // desvanecen cuando arranca el turno siguiente (mismo timing que el guion
  // de demo original).
  useEffect(() => {
    if (cards.length > 0) {
      setDisplayCards(cards)
      setCardsLeaving(false)
      return
    }
    setCardsLeaving(true)
    const id = window.setTimeout(() => {
      setDisplayCards(null)
      setCardsLeaving(false)
    }, 500)
    return () => window.clearTimeout(id)
  }, [cards])

  const showingCards =
    (displayCards !== null && !cardsLeaving) || showingPayment
  const orbState: AiOrbState = ended
    ? 'ended'
    : muted
      ? 'muted'
      : aiSpeaking
        ? 'speaking'
        : 'listening'

  const captionText = ended
    ? 'Llamada finalizada'
    : muted
      ? 'Micrófono silenciado'
      : status === 'connecting'
        ? 'Conectando con tu asesora...'
        : (caption?.text ?? 'Contanos en qué te podemos ayudar.')
  const captionIsUser = !ended && !muted && caption?.speaker === 'user'

  return (
    <div className="relative h-full min-h-[560px] overflow-hidden">
      {/* Fondo: video de bruma detrás de la animación */}
      <video
        src="/assets/bg-mist.mp4"
        autoPlay
        muted
        loop
        playsInline
        aria-hidden
        className="absolute inset-0 h-full w-full object-cover"
      />
      <div className="absolute inset-0 bg-background/65" />
      <div className="mist-overlay pointer-events-none absolute inset-0" />

      {/* Cabecera flotante */}
      <div className="absolute inset-x-0 top-0 z-20 flex items-center justify-between px-margin-mobile pt-5 md:px-margin-desktop">
        <div className="flex items-center gap-3">
          <h1 className="text-headline-md font-bold text-on-surface">
            Llamada IA
          </h1>
          <div className="rounded-full bg-primary/10 px-2.5 py-0.5 backdrop-blur-sm">
            <span className="text-label-sm uppercase text-primary">
              {ended ? 'Finalizada' : 'IA en vivo'}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="hidden flex-col text-right md:flex">
            <span className="text-label-sm text-on-surface-variant">
              Duración
            </span>
            <span className="text-label-md font-bold text-primary">
              {formatDuration(seconds)}
            </span>
          </div>
          <div className="flex size-10 items-center justify-center overflow-hidden rounded-full border-2 border-primary/20 bg-primary-container shadow-sm">
            <img
              src="/assets/avatars/call-user.png"
              alt="Usuario en llamada"
              className="h-full w-full object-cover"
            />
          </div>
        </div>
      </div>

      {/* Escenario: orbe protagonista que se hace a un lado al proyectar datos */}
      <div className="relative z-10 flex h-full items-center justify-center">
        <div
          className={`flex flex-col items-center transition-all duration-700 ease-out ${
            showingCards
              ? '-translate-y-24 scale-[0.62] sm:translate-y-0 sm:-translate-x-[46%] sm:scale-[0.78] lg:-translate-x-[54%]'
              : ''
          }`}
          style={{ '--orb-size': 'min(56vh, 30rem)' } as CSSProperties}
        >
          <AiVisualizerStub state={orbState} />
          <div className="text-center">
            <h2 className="mb-1 text-headline-md text-forest-deep">
              Asesora Tequendama
            </h2>
            <p className="flex items-center justify-center gap-2 text-label-md text-primary/70">
              <span
                className={`h-2 w-2 rounded-full ${
                  muted || ended
                    ? 'bg-outline'
                    : aiSpeaking
                      ? 'animate-pulse bg-amber-cta'
                      : 'animate-pulse bg-primary/60'
                }`}
              />
              {ended
                ? 'Llamada finalizada'
                : muted
                  ? 'Silenciado'
                  : aiSpeaking
                    ? 'Hablando...'
                    : status === 'connecting'
                      ? 'Conectando...'
                      : 'Escuchando...'}
              {sentNote ? ' · Correo marcado' : ''}
            </p>
            {error && (
              <p className="mt-2 text-label-sm text-error">{error}</p>
            )}
          </div>
        </div>

        {/* Cards proyectadas por la asesora (tool_result + payment_link CTA) */}
        {(displayCards || showingPayment) && (
          <div
            className={`absolute inset-x-4 bottom-28 z-20 flex flex-col gap-3 sm:inset-x-auto sm:right-[6%] sm:top-1/2 sm:bottom-auto sm:w-96 sm:-translate-y-1/2 lg:right-[10%] ${
              cardsLeaving && !showingPayment ? 'call-cards-leaving' : ''
            }`}
          >
            {displayCards?.map((card, i) => (
              <div
                key={`${card.label}-${i}`}
                className={`call-card glass-card rounded-2xl p-5 shadow-lg ${
                  card.tone === 'amber' ? 'border-2 border-amber-cta/60' : ''
                }`}
                style={{ animationDelay: cardsLeaving ? `${i * 60}ms` : `${i * 150}ms` }}
              >
                <div className="flex items-start gap-4">
                  <span
                    className={`flex size-11 shrink-0 items-center justify-center rounded-xl ${
                      card.tone === 'amber'
                        ? 'bg-amber-cta/20 text-secondary'
                        : 'bg-primary/10 text-primary'
                    }`}
                  >
                    <Icon name={card.icon} filled className="text-[22px]" />
                  </span>
                  <div className="min-w-0">
                    <p className="text-label-sm uppercase tracking-wide text-on-surface-variant">
                      {card.label}
                    </p>
                    <p className="text-headline-md text-on-surface">
                      {card.value}
                    </p>
                    {card.hint && (
                      <p className="mt-0.5 text-label-sm text-on-surface-variant">
                        {card.hint}
                      </p>
                    )}
                  </div>
                </div>
              </div>
            ))}
            {payment ? (
              <div className="call-card glass-card overflow-hidden rounded-2xl shadow-lg">
                <PaymentCard payment={payment} />
              </div>
            ) : null}
          </div>
        )}
      </div>

      {/* Subtítulo en vivo de la conversación */}
      {!ended && (
        <div
          className={`pointer-events-none absolute inset-x-0 bottom-28 z-10 justify-center px-margin-mobile sm:bottom-32 ${
            showingCards ? 'hidden sm:flex' : 'flex'
          }`}
        >
          <p
            key={captionText}
            className={`call-caption max-w-xl rounded-2xl bg-white/70 px-6 py-3 text-center text-body-md shadow-sm backdrop-blur-md ${
              captionIsUser ? 'italic text-on-surface-variant' : 'text-on-surface'
            } ${showingCards ? 'sm:translate-x-[-18%]' : ''}`}
          >
            {captionText}
          </p>
        </div>
      )}

      <CallControls
        muted={muted}
        onMuteToggle={toggleMute}
        onEnd={endCall}
        onSend={() => setSentNote(true)}
      />
    </div>
  )
}
