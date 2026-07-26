/**
 * "Déjanos tu número y te llamamos" — la puerta de entrada por voz de la landing.
 *
 * El visitante escribe su celular y el sistema le devuelve la llamada con el
 * agente de voz (ElevenLabs, ver apps/ai/app/callback.py). No hay login: se
 * manda el `device_id` del navegador para que la llamada se cruce con lo que
 * esa misma persona ya haya cotizado en el chat.
 *
 * Tres estados: formulario -> llamando -> resultado. Los rechazos de validación
 * vuelven como 200 con ok=false, así que se pintan bajo el campo sin sacar al
 * visitante del formulario.
 */
import { useState, type FormEvent } from 'react'
import { Icon } from '../../components/ui/Icon'
import { Reveal } from '../../components/ui/Reveal'
import { Button } from '../../components/ui/Button'
import { getDeviceId } from '../../lib/clientIdentity'
import { ADVISOR_WHATSAPP_URL } from '../../lib/contact'

type Interes = { id: string; label: string; icon: string }

// Mismos ramos que ProductCards, con el icono que ya usa cada uno.
const INTERESES: Interes[] = [
  { id: 'vida', label: 'Vida', icon: 'favorite' },
  { id: 'auto', label: 'Auto', icon: 'directions_car' },
  { id: 'salud', label: 'Salud', icon: 'health_and_safety' },
  { id: 'hogar', label: 'Hogar', icon: 'home' },
  { id: 'otro', label: 'Aún no sé', icon: 'help' },
]

type Estado =
  | { fase: 'formulario' }
  | { fase: 'llamando'; mensaje: string; demo: boolean }
  | { fase: 'error'; mensaje: string }

const inputClass =
  'w-full rounded-md border border-outline-variant bg-surface-container-lowest px-4 py-3 text-body-md text-on-surface placeholder:text-on-surface-variant/60 outline-none transition-colors focus:border-primary focus:ring-2 focus:ring-primary/20'

export function CallMeBack() {
  const [nombre, setNombre] = useState('')
  const [telefono, setTelefono] = useState('')
  const [interes, setInteres] = useState('')
  const [consent, setConsent] = useState(false)
  const [enviando, setEnviando] = useState(false)
  const [errorCampo, setErrorCampo] = useState<string | null>(null)
  const [estado, setEstado] = useState<Estado>({ fase: 'formulario' })

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    if (enviando) return
    setErrorCampo(null)
    setEnviando(true)
    try {
      const res = await fetch('/api/callback/solicitar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          telefono: telefono.trim(),
          nombre: nombre.trim(),
          interes,
          device_id: getDeviceId(),
          consent,
        }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = (await res.json()) as {
        ok: boolean
        demo?: boolean
        mensaje?: string
      }
      if (!data.ok) {
        setErrorCampo(data.mensaje ?? 'No pudimos procesar tu solicitud.')
        return
      }
      setEstado({
        fase: 'llamando',
        mensaje: data.mensaje ?? 'Te estamos llamando.',
        demo: Boolean(data.demo),
      })
    } catch {
      setEstado({
        fase: 'error',
        mensaje:
          'No pudimos conectarnos en este momento. Inténtalo de nuevo o escríbenos por WhatsApp.',
      })
    } finally {
      setEnviando(false)
    }
  }

  function reiniciar() {
    setEstado({ fase: 'formulario' })
    setErrorCampo(null)
    setConsent(false)
  }

  return (
    <section
      id="llamame"
      className="px-margin-mobile py-24 md:px-margin-desktop"
    >
      <Reveal className="mx-auto max-w-container-max">
        <div className="grid grid-cols-1 items-center gap-10 rounded-2xl border border-outline-variant/60 bg-surface-container-lowest p-6 shadow-sm md:grid-cols-2 md:gap-14 md:p-12">
          {/* Columna izquierda: la promesa */}
          <div>
            <p className="mb-2 font-hand text-xl font-semibold text-secondary">
              Sin esperas
            </p>
            <h2 className="mb-4 text-headline-lg text-primary">
              Déjanos tu número y te llamamos
            </h2>
            <p className="mb-8 max-w-md text-body-lg text-on-surface-variant">
              Escribe tu celular y nuestra asesora de voz te marca en segundos.
              Resuelve dudas, cotiza y avanza con tu póliza hablando, sin
              formularios eternos ni música de espera.
            </p>
            <ul className="space-y-3">
              {[
                { icon: 'schedule', text: 'Te llamamos en menos de un minuto' },
                { icon: 'record_voice_over', text: 'Conversación natural, no un menú de opciones' },
                { icon: 'lock', text: 'Tu número solo se usa para esta llamada' },
              ].map((f) => (
                <li key={f.icon} className="flex items-center gap-3">
                  <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <Icon name={f.icon} filled className="text-[20px]" />
                  </span>
                  <span className="text-body-md text-on-surface">{f.text}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* Columna derecha: el formulario / el resultado */}
          <div className="rounded-2xl bg-gradient-to-br from-forest-deep via-primary to-forest-deep p-6 shadow-xl md:p-8">
            {estado.fase === 'formulario' && (
              <form onSubmit={handleSubmit} className="space-y-stack-md">
                <div className="flex flex-col gap-1.5">
                  <label
                    htmlFor="cb-nombre"
                    className="text-label-sm text-white/70"
                  >
                    ¿Cómo te llamas?
                  </label>
                  <input
                    id="cb-nombre"
                    type="text"
                    autoComplete="given-name"
                    value={nombre}
                    onChange={(e) => setNombre(e.target.value)}
                    placeholder="Tu nombre"
                    className={inputClass}
                  />
                </div>

                <div className="flex flex-col gap-1.5">
                  <label
                    htmlFor="cb-telefono"
                    className="text-label-sm text-white/70"
                  >
                    Tu celular
                  </label>
                  <div className="flex items-stretch gap-2">
                    <span className="flex shrink-0 items-center rounded-md border border-outline-variant bg-surface-container-lowest px-3 text-body-md font-bold text-on-surface-variant">
                      +57
                    </span>
                    <input
                      id="cb-telefono"
                      type="tel"
                      inputMode="numeric"
                      autoComplete="tel-national"
                      required
                      value={telefono}
                      onChange={(e) => setTelefono(e.target.value)}
                      placeholder="300 123 4567"
                      aria-describedby={errorCampo ? 'cb-error' : undefined}
                      className={inputClass}
                    />
                  </div>
                </div>

                <fieldset className="flex flex-col gap-2">
                  <legend className="mb-1 text-label-sm text-white/70">
                    ¿Sobre qué quieres hablar?
                  </legend>
                  <div className="flex flex-wrap gap-2">
                    {INTERESES.map((i) => {
                      const activo = interes === i.id
                      return (
                        <button
                          key={i.id}
                          type="button"
                          onClick={() => setInteres(activo ? '' : i.id)}
                          aria-pressed={activo}
                          className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-label-md transition-all ${
                            activo
                              ? 'border-amber-cta bg-amber-cta text-primary font-bold'
                              : 'border-white/30 text-white/85 hover:border-white/60 hover:bg-white/10'
                          }`}
                        >
                          <Icon name={i.icon} className="text-[18px]" />
                          {i.label}
                        </button>
                      )
                    })}
                  </div>
                </fieldset>

                <label className="flex cursor-pointer items-start gap-3">
                  <input
                    type="checkbox"
                    required
                    checked={consent}
                    onChange={(e) => setConsent(e.target.checked)}
                    className="mt-0.5 size-5 shrink-0 accent-amber-cta"
                  />
                  <span className="text-label-sm leading-relaxed text-white/70">
                    Autorizo a Tequendama a llamarme a este número y a tratar mis
                    datos personales conforme a la Ley 1581 de 2012.
                  </span>
                </label>

                {errorCampo && (
                  <div
                    id="cb-error"
                    role="alert"
                    className="flex items-start gap-2 rounded-md bg-error-container px-3 py-2.5 text-label-md text-on-error-container"
                  >
                    <Icon name="error" className="mt-px text-[20px]" />
                    <span>{errorCampo}</span>
                  </div>
                )}

                <Button
                  type="submit"
                  variant="cta"
                  className="w-full py-3.5 text-body-lg"
                  disabled={enviando}
                >
                  {enviando ? (
                    <>
                      <span className="size-4 animate-spin rounded-full border-2 border-primary/40 border-t-primary" />
                      Conectando…
                    </>
                  ) : (
                    <>
                      <Icon name="call" filled className="text-[22px]" />
                      Llámame ahora
                    </>
                  )}
                </Button>
              </form>
            )}

            {estado.fase === 'llamando' && (
              <div className="flex flex-col items-center py-6 text-center">
                <span className="relative mb-6 flex size-20 items-center justify-center">
                  <span
                    className="absolute inset-0 animate-ping rounded-full bg-amber-cta/40"
                    aria-hidden
                  />
                  <span className="relative flex size-20 items-center justify-center rounded-full bg-amber-cta text-primary">
                    <Icon name="phone_in_talk" filled className="text-[36px]" />
                  </span>
                </span>
                <h3 className="mb-2 font-display text-headline-md text-white">
                  {estado.demo ? 'Solicitud registrada' : 'Te estamos llamando'}
                </h3>
                <p className="mb-8 max-w-xs text-body-md text-white/75">
                  {estado.mensaje}
                </p>
                <button
                  type="button"
                  onClick={reiniciar}
                  className="text-label-md font-bold text-amber-cta underline-offset-4 hover:underline"
                >
                  Pedir otra llamada
                </button>
              </div>
            )}

            {estado.fase === 'error' && (
              <div className="flex flex-col items-center py-6 text-center">
                <span className="mb-6 flex size-20 items-center justify-center rounded-full bg-white/10 text-white">
                  <Icon name="phone_disabled" filled className="text-[36px]" />
                </span>
                <h3 className="mb-2 font-display text-headline-md text-white">
                  No pudimos llamarte
                </h3>
                <p className="mb-8 max-w-xs text-body-md text-white/75">
                  {estado.mensaje}
                </p>
                <div className="flex flex-col items-center gap-3">
                  <Button type="button" variant="cta" onClick={reiniciar}>
                    <Icon name="refresh" className="text-[20px]" />
                    Reintentar
                  </Button>
                  <a
                    href={ADVISOR_WHATSAPP_URL}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-label-md font-bold text-white/80 underline-offset-4 hover:underline"
                  >
                    Escribirnos por WhatsApp
                  </a>
                </div>
              </div>
            )}
          </div>
        </div>
      </Reveal>
    </section>
  )
}
