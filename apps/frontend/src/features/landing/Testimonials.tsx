import { Icon } from '../../components/ui/Icon'
import { Reveal } from '../../components/ui/Reveal'

const testimonials = [
  {
    avatar: '/assets/avatars/elena.png',
    name: 'Elena Ramírez',
    role: 'Seguro de Vida · Bogotá',
    quote:
      'Coticé mi seguro de vida en una sola llamada, un domingo a las 9 de la noche. La IA entendió todo a la primera y al día siguiente ya tenía mi póliza en el correo.',
  },
  {
    avatar: '/assets/avatars/julian.png',
    name: 'Julián Herrera',
    role: 'Seguro de Auto · Medellín',
    quote:
      'Tuve un choque leve y la asistencia respondió en menos de un minuto. La grúa llegó rápido y el reclamo se resolvió por chat, sin una sola llamada en espera.',
  },
  {
    avatar: '/assets/avatars/sofia.png',
    name: 'Sofía Cárdenas',
    role: 'Seguro de Salud · Cali',
    quote:
      'Comparé tres planes de salud hablando con el asistente como si fuera un amigo. Me explicó las diferencias sin jerga y el pago en línea fue de dos toques.',
  },
]

export function Testimonials() {
  return (
    <section
      id="opiniones"
      className="bg-mist-white px-margin-mobile py-24 md:px-margin-desktop"
    >
      <div className="mx-auto max-w-container-max">
        <Reveal className="mx-auto mb-16 max-w-2xl text-center">
          <p className="mb-2 font-hand text-xl font-semibold text-secondary">
            Historias reales
          </p>
          <h2 className="mb-4 text-headline-lg text-primary">
            Personas que ya fluyen protegidas
          </h2>
          <p className="text-body-md text-on-surface-variant">
            Miles de colombianos ya confían su tranquilidad a Tequendama. Esto
            es lo que cuentan.
          </p>
        </Reveal>
        <div className="grid grid-cols-1 gap-gutter md:grid-cols-3">
          {testimonials.map((t, i) => (
            <Reveal key={t.name} delay={i * 140} className="h-full">
              <figure className="glass-card hover-lift flex h-full flex-col rounded-lg p-8">
                <div
                  className="mb-4 flex gap-0.5 text-amber-cta"
                  role="img"
                  aria-label="Calificación: 5 de 5 estrellas"
                >
                  {Array.from({ length: 5 }, (_, star) => (
                    <Icon key={star} name="star" filled className="text-[20px]" />
                  ))}
                </div>
                <blockquote className="flex-grow text-body-md text-on-surface">
                  “{t.quote}”
                </blockquote>
                <figcaption className="mt-6 flex items-center gap-3 border-t border-outline-variant/30 pt-6">
                  <img
                    src={t.avatar}
                    alt={t.name}
                    className="size-11 rounded-full object-cover"
                    loading="lazy"
                  />
                  <div className="flex flex-col">
                    <span className="text-label-md font-bold text-primary">
                      {t.name}
                    </span>
                    <span className="text-label-sm text-on-surface-variant">
                      {t.role}
                    </span>
                  </div>
                </figcaption>
              </figure>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  )
}
