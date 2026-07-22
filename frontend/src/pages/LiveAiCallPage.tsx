import { useState } from 'react'
import { AiVisualizerStub } from '../features/call/AiVisualizerStub'
import { TranscriptPanel } from '../features/call/TranscriptPanel'
import { QuoteBuilder } from '../features/call/QuoteBuilder'
import { CallControls } from '../features/call/CallControls'
import { callQuote, callTranscript } from '../data/mock/call'

export function LiveAiCallPage() {
  const [muted, setMuted] = useState(false)
  const [ended, setEnded] = useState(false)
  const [sentNote, setSentNote] = useState(false)

  return (
    <>
      <header className="fixed top-0 z-50 flex w-full items-center justify-between bg-surface/80 px-margin-mobile py-4 shadow-sm backdrop-blur-md md:px-margin-desktop">
        <div className="flex items-center gap-2">
          <span className="text-display-lg-mobile font-extrabold tracking-tighter text-primary md:text-display-lg">
            Tequendama
          </span>
          <div className="rounded-full bg-primary/10 px-2 py-0.5">
            <span className="text-label-sm uppercase text-primary">
              {ended ? 'Finalizada' : 'IA en vivo'}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="hidden flex-col text-right md:flex">
            <span className="text-label-md text-on-surface-variant">
              Duración
            </span>
            <span className="text-label-sm font-bold text-primary">03:45</span>
          </div>
          <div className="flex size-10 items-center justify-center overflow-hidden rounded-full border-2 border-primary/20 bg-primary-container text-white shadow-sm">
            <img
              src="/assets/avatars/call-user.png"
              alt="Usuario en llamada"
              className="h-full w-full object-cover"
            />
          </div>
        </div>
      </header>

      <main className="relative mx-auto grid w-full max-w-container-max flex-grow grid-cols-1 gap-gutter px-margin-mobile pt-24 pb-32 md:px-margin-desktop lg:grid-cols-12">
        <div className="mist-overlay pointer-events-none absolute inset-0" />
        <div className="z-10 flex flex-col gap-stack-lg lg:col-span-7">
          <div className="relative flex min-h-[400px] flex-col items-center justify-center rounded-3xl border border-white/50 bg-white/40 p-stack-lg shadow-sm backdrop-blur-sm">
            <AiVisualizerStub />
            <div className="text-center">
              <h2 className="mb-1 text-headline-md text-forest-deep">
                Asesora Tequendama
              </h2>
              <p className="flex items-center justify-center gap-2 text-label-md text-primary/70">
                <span
                  className={`h-2 w-2 rounded-full ${muted || ended ? 'bg-outline' : 'animate-pulse bg-amber-cta'}`}
                />
                {ended
                  ? 'Llamada finalizada'
                  : muted
                    ? 'Silenciado'
                    : 'Escuchando...'}
                {sentNote ? ' · Correo marcado' : ''}
              </p>
            </div>
          </div>
          <TranscriptPanel lines={callTranscript} />
        </div>
        <QuoteBuilder quote={callQuote} />
      </main>

      <CallControls
        muted={muted}
        onMuteToggle={() => setMuted((v) => !v)}
        onEnd={() => setEnded(true)}
        onSend={() => setSentNote(true)}
      />
    </>
  )
}
