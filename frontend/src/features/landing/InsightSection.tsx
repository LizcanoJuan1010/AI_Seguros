import { Icon } from '../../components/ui/Icon'
import { Button } from '../../components/ui/Button'

export function InsightSection() {
  return (
    <section className="mx-auto max-w-container-max px-margin-mobile py-24 md:px-margin-desktop">
      <div className="grid grid-cols-1 items-center gap-16 lg:grid-cols-2">
        <div className="relative aspect-[4/3] overflow-hidden rounded-2xl shadow-2xl">
          <img
            src="/assets/insight-hero.png"
            alt="Profesional de seguros con visualización de datos estilo cascada"
            className="h-full w-full object-cover"
          />
          <div className="absolute inset-0 bg-gradient-to-t from-primary/60 to-transparent" />
          <div className="glass-card absolute right-8 bottom-8 left-8 rounded-lg p-6">
            <p className="mb-2 flex items-center gap-2 text-label-sm text-primary">
              <Icon name="bolt" className="text-[16px]" /> ACTUALIZACIÓN EN
              TIEMPO REAL
            </p>
            <h4 className="mb-2 text-headline-md text-on-surface">
              Pólizas dinámicas
            </h4>
            <p className="text-body-md text-on-surface-variant">
              Nuestra IA ajusta tus primas basándose en tu comportamiento real,
              ahorrándote hasta un 15% mensual.
            </p>
          </div>
        </div>
        <div className="space-y-stack-lg">
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
          <div className="grid grid-cols-2 gap-stack-md">
            <div className="rounded-lg border border-outline-variant/30 bg-white p-6 shadow-sm">
              <p className="mb-1 text-display-lg-mobile font-bold text-secondary">
                99%
              </p>
              <p className="text-label-md text-on-surface-variant">
                Satisfacción al cliente
              </p>
            </div>
            <div className="rounded-lg border border-outline-variant/30 bg-white p-6 shadow-sm">
              <p className="mb-1 text-display-lg-mobile font-bold text-secondary">
                2ms
              </p>
              <p className="text-label-md text-on-surface-variant">
                Latencia de IA
              </p>
            </div>
          </div>
          <Button variant="ghost" className="rounded-md px-8 py-4">
            Hablar con un consultor experto
            <Icon name="person" />
          </Button>
        </div>
      </div>
    </section>
  )
}
