import { Link } from 'react-router-dom'
import { Icon } from '../../components/ui/Icon'
import { Button } from '../../components/ui/Button'

export function HeroStub() {
  return (
    <section className="relative flex min-h-[85vh] flex-col items-center justify-center overflow-hidden px-margin-mobile text-center md:px-margin-desktop">
      <div className="hero-mist absolute inset-0 -z-10 opacity-40" aria-hidden />
      <div className="relative z-10 mx-auto max-w-4xl space-y-stack-lg">
        <div className="inline-flex items-center gap-2 rounded-full border border-outline-variant bg-surface-container-high/50 px-4 py-1.5 backdrop-blur-sm">
          <span className="h-2 w-2 animate-pulse rounded-full bg-secondary-container" />
          <span className="text-label-sm uppercase tracking-widest text-primary">
            Asistencia IA disponible 24/7
          </span>
        </div>
        <h1 className="text-display-lg-mobile leading-tight tracking-tight text-primary md:text-display-lg">
          Tu seguro, <br className="md:hidden" />{' '}
          <span className="italic text-secondary">a una llamada</span> de
          distancia.
        </h1>
        <p className="mx-auto max-w-2xl text-body-lg text-on-surface-variant">
          Experimenta el futuro de la protección con nuestra IA especializada.
          Sencillo, fluido y humano, inspirado en la fuerza natural del Salto
          del Tequendama.
        </p>
        <div className="flex flex-col items-center justify-center gap-stack-md pt-8 md:flex-row">
          <Link
            to="/llamada"
            className="group inline-flex items-center gap-4 rounded-md bg-amber-cta px-10 py-5 text-headline-md font-bold text-primary shadow-xl shadow-amber-cta/20 transition-all hover:scale-105 active:scale-95"
          >
            <Icon
              name="call"
              filled
              className="text-[32px] transition-transform group-hover:rotate-12"
            />
            Hablar con un asesor IA
          </Link>
          <Button variant="ghost" className="rounded-md px-10 py-5 text-headline-md">
            Explorar Planes
          </Button>
        </div>
      </div>
    </section>
  )
}
