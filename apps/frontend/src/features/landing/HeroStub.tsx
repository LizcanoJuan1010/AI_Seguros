import { Link } from 'react-router-dom'
import { Icon } from '../../components/ui/Icon'

const proofAvatars = [
  { src: '/assets/avatars/elena.png', alt: 'Elena, clienta de Tequendama' },
  { src: '/assets/avatars/julian.png', alt: 'Julián, cliente de Tequendama' },
  { src: '/assets/avatars/sofia.png', alt: 'Sofía, clienta de Tequendama' },
]

export function HeroStub() {
  return (
    <section className="relative flex min-h-[88svh] flex-col items-center justify-center overflow-hidden px-margin-mobile pb-24 pt-28 text-center md:px-margin-desktop md:pt-32">
      <div className="hero-mist absolute inset-0 -z-10 opacity-40" aria-hidden />
      <div className="relative z-10 mx-auto w-full max-w-4xl space-y-stack-lg">
        <div className="inline-flex items-center gap-2 rounded-full border border-outline-variant bg-surface-container-high/50 px-4 py-1.5 backdrop-blur-sm">
          <span className="h-2 w-2 animate-pulse rounded-full bg-secondary-container" />
          <span className="text-label-sm uppercase tracking-widest text-primary">
            Asistencia IA disponible 24/7
          </span>
        </div>
        <h1 className="text-display-lg-mobile leading-tight tracking-tight text-primary md:text-display-lg">
          Tu seguro, <br className="md:hidden" />{' '}
          <span className="font-hand font-semibold text-secondary">
            a una llamada
          </span>{' '}
          de distancia.
        </h1>
        <p className="mx-auto max-w-2xl text-body-lg text-on-surface-variant">
          Experimenta el futuro de la protección con nuestra IA especializada.
          Sencillo, fluido y humano, inspirado en la fuerza natural del Salto
          del Tequendama.
        </p>
        <div className="flex flex-col items-center justify-center gap-stack-md pt-6 sm:flex-row">
          <Link
            to="/llamada"
            className="group inline-flex w-full items-center justify-center gap-3 rounded-md bg-amber-cta px-8 py-4 text-body-lg font-bold text-primary shadow-xl shadow-amber-cta/20 transition-all hover:scale-105 active:scale-95 sm:w-auto md:px-10 md:py-5 md:text-headline-md"
          >
            <Icon
              name="call"
              filled
              className="text-[26px] transition-transform group-hover:rotate-12 md:text-[30px]"
            />
            Hablar con un asesor IA
          </Link>
          <a
            href="#planes"
            className="inline-flex w-full items-center justify-center gap-2 rounded-md border-2 border-primary px-8 py-4 text-body-lg font-bold text-primary transition-colors hover:bg-primary/5 sm:w-auto md:px-10 md:py-5 md:text-headline-md"
          >
            Explorar planes
          </a>
        </div>
        <div className="flex flex-col items-center justify-center gap-3 pt-4 sm:flex-row">
          <div className="flex -space-x-3">
            {proofAvatars.map((avatar) => (
              <img
                key={avatar.src}
                src={avatar.src}
                alt={avatar.alt}
                className="size-10 rounded-full border-2 border-surface object-cover shadow-sm"
                loading="lazy"
              />
            ))}
          </div>
          <p className="text-label-md text-on-surface-variant">
            <span className="font-bold text-primary">+12.000 personas</span>{' '}
            protegidas en Colombia
          </p>
        </div>
      </div>

      <a
        href="#planes"
        aria-label="Ver los planes"
        className="absolute bottom-6 left-1/2 hidden -translate-x-1/2 flex-col items-center gap-1 text-on-surface-variant transition-colors hover:text-primary motion-safe:animate-bounce md:flex"
      >
        <Icon name="keyboard_arrow_down" className="text-[28px]" />
      </a>
    </section>
  )
}
