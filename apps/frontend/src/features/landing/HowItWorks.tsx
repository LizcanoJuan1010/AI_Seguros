import { Icon } from '../../components/ui/Icon'
import { Reveal } from '../../components/ui/Reveal'

const steps = [
  {
    number: '01',
    icon: 'forum',
    title: 'Cuéntanos qué necesitas',
    body: 'Escríbele al asistente o llama a nuestra IA. Sin formularios eternos: una conversación natural basta para entender tu caso.',
  },
  {
    number: '02',
    icon: 'psychology',
    title: 'La IA diseña tu plan',
    body: 'En segundos comparamos coberturas y armamos una propuesta a tu medida, con precios claros y sin letra pequeña.',
  },
  {
    number: '03',
    icon: 'verified_user',
    title: 'Protegido al instante',
    body: 'Paga de forma segura en línea y recibe tu póliza en el correo en minutos. Tu protección empieza de inmediato.',
  },
]

export function HowItWorks() {
  return (
    <section
      id="como-funciona"
      className="px-margin-mobile py-24 md:px-margin-desktop"
    >
      <div className="mx-auto max-w-container-max">
        <Reveal className="mx-auto mb-16 max-w-2xl text-center">
          <p className="mb-2 font-hand text-xl font-semibold text-secondary">
            Así de simple
          </p>
          <h2 className="mb-4 text-headline-lg text-primary">
            Protegido en tres pasos
          </h2>
          <p className="text-body-md text-on-surface-variant">
            Olvídate de trámites infinitos y llamadas en espera. Nuestro
            proceso está diseñado para que asegures lo que más quieres en
            minutos, no en semanas.
          </p>
        </Reveal>
        <div className="relative grid grid-cols-1 gap-gutter md:grid-cols-3">
          {/* Línea conectora entre pasos (solo desktop) */}
          <div
            className="absolute left-[16%] right-[16%] top-10 hidden border-t-2 border-dashed border-outline-variant/60 md:block"
            aria-hidden
          />
          {steps.map((step, i) => (
            <Reveal key={step.number} delay={i * 160} className="h-full">
              <article className="relative flex h-full flex-col items-center rounded-lg p-6 text-center md:p-8">
                <div className="relative mb-6 flex size-20 items-center justify-center rounded-full border border-outline-variant/40 bg-surface-container-lowest shadow-md">
                  <Icon name={step.icon} filled className="text-[34px] text-primary" />
                  <span className="absolute -right-1 -top-1 flex size-8 items-center justify-center rounded-full bg-amber-cta text-label-sm font-bold text-primary shadow-sm">
                    {step.number}
                  </span>
                </div>
                <h3 className="mb-3 text-headline-md text-primary">
                  {step.title}
                </h3>
                <p className="text-body-md text-on-surface-variant">
                  {step.body}
                </p>
              </article>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  )
}
