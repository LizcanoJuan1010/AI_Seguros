import { Icon } from '../../components/ui/Icon'
import { Button } from '../../components/ui/Button'
import { Reveal } from '../../components/ui/Reveal'
import { CountUp } from '../../components/ui/CountUp'

export function InsightSection() {
  return (
    <section className="mx-auto max-w-container-max px-margin-mobile py-24 md:px-margin-desktop">
      <div className="grid grid-cols-1 items-center gap-16 lg:grid-cols-2">
        <Reveal>
          <div className="relative aspect-video overflow-hidden rounded-2xl shadow-2xl">
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
          <div className="grid grid-cols-2 gap-stack-md">
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
            <Button variant="ghost" className="rounded-md px-8 py-4">
              Hablar con un consultor experto
              <Icon name="person" />
            </Button>
          </Reveal>
        </div>
      </div>
    </section>
  )
}
