import { Link } from 'react-router-dom'
import { Icon } from '../../components/ui/Icon'
import { Reveal } from '../../components/ui/Reveal'
import { CountUp } from '../../components/ui/CountUp'
import { WhatsAppIcon } from '../../components/ui/WhatsAppIcon'
import {
  ADVISOR_WHATSAPP_DISPLAY,
  ADVISOR_WHATSAPP_URL,
} from '../../lib/contact'

const stats = [
  { end: 12000, prefix: '+', suffix: '', label: 'Personas protegidas' },
  { end: 30, prefix: '<', suffix: 's', label: 'Tiempo de respuesta' },
  { end: 99, prefix: '', suffix: '%', label: 'Satisfacción' },
]

export function CtaBand() {
  return (
    <section className="px-margin-mobile pb-8 pt-4 md:px-margin-desktop">
      <Reveal className="mx-auto max-w-container-max">
        <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-forest-deep via-primary to-forest-deep px-6 py-16 text-center shadow-2xl md:px-16 md:py-20">
          {/* Halos decorativos */}
          <div
            className="pointer-events-none absolute -left-24 -top-24 size-72 rounded-full bg-amber-cta/15 blur-3xl"
            aria-hidden
          />
          <div
            className="pointer-events-none absolute -bottom-32 -right-16 size-80 rounded-full bg-inverse-primary/20 blur-3xl"
            aria-hidden
          />
          <div className="relative z-10 mx-auto max-w-3xl">
            <p className="mb-3 font-hand text-xl font-semibold text-secondary-container">
              Empieza hoy
            </p>
            <h2 className="mb-4 font-display text-display-lg-mobile text-white md:text-display-lg">
              ¿Listo para sentirte protegido?
            </h2>
            <p className="mx-auto mb-10 max-w-xl text-body-lg text-white/80">
              Habla con nuestra IA ahora mismo y descubre en minutos el plan
              que mejor cuida lo que más quieres.
            </p>
            <div className="flex flex-col items-center justify-center gap-stack-md sm:flex-row">
              <Link
                to="/llamada"
                className="group inline-flex w-full items-center justify-center gap-3 rounded-md bg-amber-cta px-8 py-4 text-body-lg font-bold text-primary shadow-xl shadow-black/20 transition-all hover:scale-105 active:scale-95 sm:w-auto"
              >
                <Icon
                  name="call"
                  filled
                  className="text-[24px] transition-transform group-hover:rotate-12"
                />
                Hablar con un asesor IA
              </Link>
              <a
                href="#planes"
                className="inline-flex w-full items-center justify-center gap-2 rounded-md border-2 border-white/60 px-8 py-4 text-body-lg font-bold text-white transition-colors hover:border-white hover:bg-white/10 sm:w-auto"
              >
                Ver planes
              </a>
            </div>
            {/* WhatsApp del asesor humano: opción de escribir directamente */}
            <a
              href={ADVISOR_WHATSAPP_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="group mt-8 inline-flex max-w-full items-center gap-3 rounded-full border border-white/25 bg-white/10 py-2 pl-2 pr-6 text-left backdrop-blur-sm transition-all hover:border-[#25d366]/70 hover:bg-[#25d366]/15"
            >
              <span className="flex size-11 shrink-0 items-center justify-center rounded-full bg-[#25d366] text-white shadow-md shadow-black/25 transition-transform group-hover:scale-110">
                <WhatsAppIcon className="size-6" />
              </span>
              <span className="flex min-w-0 flex-col">
                <span className="text-label-sm text-white/70">
                  ¿Prefieres escribir? Chatea con un asesor
                </span>
                <span className="truncate text-body-md font-bold text-white">
                  {ADVISOR_WHATSAPP_DISPLAY}
                </span>
              </span>
            </a>
            <dl className="mt-12 grid grid-cols-1 gap-6 border-t border-white/15 pt-10 sm:grid-cols-3">
              {stats.map((stat) => (
                <div key={stat.label} className="flex flex-col items-center gap-1">
                  <dt className="sr-only">{stat.label}</dt>
                  <dd className="font-display text-headline-lg font-bold text-white">
                    <CountUp
                      end={stat.end}
                      prefix={stat.prefix}
                      suffix={stat.suffix}
                    />
                  </dd>
                  <span className="text-label-md text-white/70">
                    {stat.label}
                  </span>
                </div>
              ))}
            </dl>
          </div>
        </div>
      </Reveal>
    </section>
  )
}
