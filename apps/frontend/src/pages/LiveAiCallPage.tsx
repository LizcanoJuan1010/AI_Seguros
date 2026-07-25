import { useEffect, useState, type CSSProperties } from 'react'
import { useNavigate } from 'react-router-dom'
import { AiVisualizerStub, type AiOrbState } from '../features/call/AiVisualizerStub'
import { CallControls } from '../features/call/CallControls'
import { Icon } from '../components/ui/Icon'

type CallCard = {
  icon: string
  label: string
  value: string
  hint?: string
  tone?: 'amber'
}

type CallStep = {
  speaker: 'ai' | 'user'
  text: string
  dur: number
  /** Datos que la asesora proyecta al lado del orbe durante este paso. */
  cards?: CallCard[]
}

/**
 * Guion demo de la llamada (voz-primero, estilo Gemini Live / modo voz GPT):
 * el orbe protagoniza la pantalla; cuando el cliente pregunta por su cuenta
 * o por valores, la asesora proyecta cards y el orbe se hace a un lado;
 * al seguir la conversación las cards se desvanecen y el orbe vuelve al centro.
 */
const STEPS: CallStep[] = [
  {
    speaker: 'ai',
    text: 'Hola, soy tu asesora Tequendama. ¿En qué te puedo ayudar hoy?',
    dur: 4200,
  },
  {
    speaker: 'user',
    text: '"Hola, quiero saber cómo va mi cuenta."',
    dur: 3200,
  },
  {
    speaker: 'ai',
    text: 'Claro. Este es el estado de tu cuenta al día de hoy:',
    dur: 7500,
    cards: [
      {
        icon: 'directions_car',
        label: 'Póliza activa',
        value: 'Auto · Mazda CX-30',
        hint: 'Vigente hasta jul 2027',
      },
      {
        icon: 'task_alt',
        label: 'Pagos',
        value: 'Al día',
        hint: 'Próxima cuota: 05 de agosto',
      },
      {
        icon: 'savings',
        label: 'Ahorro acumulado con IA',
        value: '$312.000 COP',
        hint: 'Desde el inicio de tu póliza',
        tone: 'amber',
      },
    ],
  },
  {
    speaker: 'user',
    text: '"¿Y cuánto me costaría agregar la cobertura de viajes a la costa?"',
    dur: 3600,
  },
  {
    speaker: 'ai',
    text: 'Con cobertura nacional de viajes, tu mensualidad quedaría así:',
    dur: 7500,
    cards: [
      {
        icon: 'payments',
        label: 'Mensualidad actual',
        value: '$185.000 COP',
      },
      {
        icon: 'add_road',
        label: 'Con cobertura de viajes',
        value: '$198.500 COP',
        hint: '+$13.500 · asistencia 24/7 en carretera',
      },
      {
        icon: 'auto_awesome',
        label: 'Ahorro IA aplicado',
        value: '15%',
        hint: 'Por buen comportamiento de manejo',
        tone: 'amber',
      },
    ],
  },
  {
    speaker: 'user',
    text: '"Me parece bien, déjame pensarlo y te confirmo."',
    dur: 3400,
  },
  {
    speaker: 'ai',
    text: 'Perfecto, queda guardada la cotización. ¿Te ayudo con algo más?',
    dur: 4200,
  },
]

function formatDuration(s: number): string {
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}

/**
 * Transcripción en vivo: revela el texto del paso carácter a carácter, como
 * si la asesora/cliente estuvieran siendo transcritos en tiempo real. La
 * velocidad se ajusta para terminar dentro del ~55% de la duración del paso.
 */
function useTranscript(text: string, active: boolean, stepMs: number) {
  const [count, setCount] = useState(0)

  useEffect(() => {
    if (!active || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setCount(text.length)
      return
    }
    setCount(0)
    const perChar = Math.min(36, Math.max(12, (stepMs * 0.55) / Math.max(text.length, 1)))
    const id = window.setInterval(() => {
      setCount((c) => {
        if (c >= text.length) {
          window.clearInterval(id)
          return c
        }
        return c + 1
      })
    }, perChar)
    return () => window.clearInterval(id)
  }, [text, active, stepMs])

  return { shown: text.slice(0, count), typing: count < text.length }
}

export function LiveAiCallPage() {
  const [muted, setMuted] = useState(false)
  const [ended, setEnded] = useState(false)
  const [stepIndex, setStepIndex] = useState(0)
  const [seconds, setSeconds] = useState(0)
  const [cards, setCards] = useState<CallCard[] | null>(null)
  const [cardsLeaving, setCardsLeaving] = useState(false)

  const step = STEPS[stepIndex]
  const aiSpeaking = step.speaker === 'ai' && !muted && !ended
  const transcript = useTranscript(step.text, !muted && !ended, step.dur)

  // Avanza el guion demo mientras la llamada esté activa.
  useEffect(() => {
    if (muted || ended) return
    const id = window.setTimeout(
      () => setStepIndex((i) => (i + 1) % STEPS.length),
      step.dur,
    )
    return () => window.clearTimeout(id)
  }, [stepIndex, muted, ended, step.dur])

  // Cronómetro real de la llamada.
  useEffect(() => {
    if (ended) return
    const id = window.setInterval(() => setSeconds((s) => s + 1), 1000)
    return () => window.clearInterval(id)
  }, [ended])

  // Al colgar, la pantalla se disuelve en la bruma (clase call-leaving) y
  // ~1s después volvemos al chat (estilo modo voz de Gemini/Claude).
  const navigate = useNavigate()
  useEffect(() => {
    if (!ended) return
    const id = window.setTimeout(() => navigate('/asistente'), 1000)
    return () => window.clearTimeout(id)
  }, [ended, navigate])

  // Proyección de cards: entran con el paso que las trae y se desvanecen
  // cuando la conversación sigue.
  useEffect(() => {
    const next = step.cards ?? null
    if (next) {
      setCards(next)
      setCardsLeaving(false)
      return
    }
    setCardsLeaving(true)
    const id = window.setTimeout(() => {
      setCards(null)
      setCardsLeaving(false)
    }, 500)
    return () => window.clearTimeout(id)
  }, [stepIndex, step.cards])

  const showingCards = cards !== null && !cardsLeaving
  const orbState: AiOrbState = ended
    ? 'ended'
    : muted
      ? 'muted'
      : aiSpeaking
        ? 'speaking'
        : 'listening'

  return (
    <div
      className={`relative h-full min-h-[560px] overflow-hidden ${
        ended ? 'call-leaving' : ''
      }`}
    >
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
        <div className="flex flex-col text-right">
          <span className="text-label-sm text-on-surface-variant">
            Duración
          </span>
          <span className="text-label-md font-bold text-primary">
            {formatDuration(seconds)}
          </span>
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
                ? 'Llamada finalizada · volviendo al chat…'
                : muted
                  ? 'Silenciado'
                  : aiSpeaking
                    ? 'Hablando...'
                    : 'Escuchando...'}
            </p>
          </div>
        </div>

        {/* Cards proyectadas por la asesora */}
        {cards && (
          <div
            className={`absolute inset-x-4 bottom-40 z-20 flex flex-col gap-3 sm:inset-x-auto sm:right-[6%] sm:top-1/2 sm:bottom-auto sm:w-96 sm:-translate-y-1/2 lg:right-[10%] ${
              cardsLeaving ? 'call-cards-leaving' : ''
            }`}
          >
            {cards.map((card, i) => (
              <div
                key={`${stepIndex}-${card.label}`}
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
          </div>
        )}
      </div>

      {/* Subtítulo en vivo de la conversación */}
      {!ended && (
        <div
          className={`pointer-events-none absolute inset-x-0 bottom-40 z-10 justify-center px-margin-mobile sm:bottom-32 ${
            showingCards ? 'hidden sm:flex' : 'flex'
          }`}
        >
          <p
            key={stepIndex}
            className={`call-caption max-w-xl rounded-2xl bg-white/70 px-6 py-3 text-center text-body-md shadow-sm backdrop-blur-md ${
              step.speaker === 'user'
                ? 'italic text-on-surface-variant'
                : 'text-on-surface'
            } ${showingCards ? 'sm:translate-x-[-18%]' : ''}`}
          >
            {muted ? 'Micrófono silenciado' : transcript.shown}
            {!muted && transcript.typing && (
              <span className="transcript-caret" aria-hidden />
            )}
          </p>
        </div>
      )}

      <CallControls
        muted={muted}
        onMuteToggle={() => setMuted((v) => !v)}
        onEnd={() => setEnded(true)}
      />
    </div>
  )
}
