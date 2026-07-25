import { Icon } from '../../components/ui/Icon'
import { Reveal } from '../../components/ui/Reveal'
import { CountUp } from '../../components/ui/CountUp'

/** Capacidades de la plataforma que resumen lo que hace la IA. */
const capabilities = [
  { icon: 'support_agent', label: 'Agente IA 24/7' },
  { icon: 'bolt', label: 'Automatización de procesos' },
  { icon: 'request_quote', label: 'Cotización instantánea' },
  { icon: 'workspace_premium', label: 'Emisión de pólizas sin humanos' },
  { icon: 'health_and_safety', label: 'Siniestros asistidos por IA' },
  { icon: 'chat', label: 'Atención por WhatsApp y voz' },
]

export function InsightSection() {
  return (
    <section className="mx-auto max-w-container-max px-margin-mobile py-24 md:px-margin-desktop">
      <div className="grid grid-cols-1 items-center gap-12 lg:grid-cols-[1.35fr_1fr] lg:gap-16">
        <Reveal>
          <div className="relative aspect-[4/3] overflow-hidden rounded-2xl shadow-2xl md:aspect-[5/4] lg:aspect-[4/3]">
            <video
              src="/assets/insight-hero.mp4"
              poster="/assets/insight-hero-poster.jpg"
              autoPlay
              muted
              loop
              playsInline
              aria-label="Cliente recibiendo la información de su seguro por chat mientras camina"
              className="h-full w-full object-cover"
            />
          </div>
        </Reveal>
        <div className="space-y-stack-lg">
          <Reveal delay={120}>
            <div className="rounded-2xl border-l-4 border-primary bg-surface-container-low p-6">
              <Icon name="psychology" filled className="mb-4 text-primary" />
              <h3 className="mb-2 text-headline-md text-primary">
                Salto Angel Insights
              </h3>
              <p className="text-body-md text-on-surface-variant">
                No solo vendemos seguros; anticipamos riesgos. Nuestra tecnología
                patentada analiza millones de datos para avisarte antes de que
                algo ocurra.
              </p>
            </div>
          </Reveal>
          <div className="grid grid-cols-1 gap-stack-md xs:grid-cols-2">
            <Reveal delay={240}>
              <div className="h-full rounded-lg border border-outline-variant/30 bg-white p-6 shadow-sm">
                <p className="mb-1 text-display-lg-mobile font-bold text-secondary">
                  <CountUp end={99} suffix="%" />
                </p>
                <p className="text-label-md text-on-surface-variant">
                  Satisfacción al cliente
                </p>
              </div>
            </Reveal>
            <Reveal delay={360}>
              <div className="h-full rounded-lg border border-outline-variant/30 bg-white p-6 shadow-sm">
                <p className="mb-1 text-display-lg-mobile font-bold text-secondary">
                  2ms
                </p>
                <p className="text-label-md text-on-surface-variant">
                  Latencia de IA
                </p>
              </div>
            </Reveal>
          </div>
          <Reveal delay={480}>
            <ul className="flex flex-wrap gap-2.5">
              {capabilities.map((c) => (
                <li
                  key={c.label}
                  className="inline-flex items-center gap-2 rounded-full border border-outline-variant/50 bg-surface-container-lowest/70 px-3.5 py-2 text-label-md text-on-surface"
                >
                  <Icon name={c.icon} filled className="text-[18px] text-primary" />
                  {c.label}
                </li>
              ))}
            </ul>
          </Reveal>
        </div>
      </div>
    </section>
  )
}
