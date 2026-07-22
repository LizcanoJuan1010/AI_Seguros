import { Icon } from '../../components/ui/Icon'
import { Button } from '../../components/ui/Button'

const products = [
  {
    icon: 'favorite',
    title: 'Seguro de Vida',
    body: 'Asegura el bienestar de los que más amas con una póliza flexible que crece con tu familia.',
    points: ['Cobertura global', 'Sin exámenes tediosos'],
    cta: 'Cotizar Vida',
  },
  {
    icon: 'directions_car',
    title: 'Seguro de Auto',
    body: 'Protección total en la vía con asistencia IA inmediata para accidentes y grúas.',
    points: ['Asistencia 24/7', 'Chofer de reemplazo'],
    cta: 'Cotizar Auto',
  },
  {
    icon: 'health_and_safety',
    title: 'Seguro de Salud',
    body: 'Acceso a las mejores clínicas y especialistas con reembolso asistido por inteligencia artificial.',
    points: ['Telemedicina incluida', 'Amplia red nacional'],
    cta: 'Cotizar Salud',
  },
]

export function ProductCards() {
  return (
    <section className="bg-mist-white px-margin-mobile py-24 md:px-margin-desktop">
      <div className="mx-auto max-w-container-max">
        <div className="mb-16 flex flex-col items-end justify-between gap-6 md:flex-row">
          <div className="max-w-xl">
            <h2 className="mb-4 text-headline-lg text-primary">
              Protección que fluye contigo
            </h2>
            <p className="text-body-md text-on-surface-variant">
              Selecciona el área que deseas proteger hoy. Nuestra IA te guiará
              para encontrar la cobertura perfecta sin trámites infinitos.
            </p>
          </div>
          <a
            href="#ramos"
            className="flex items-center gap-2 font-bold text-primary hover:underline"
          >
            Ver todos los ramos <Icon name="arrow_forward" />
          </a>
        </div>
        <div id="ramos" className="grid grid-cols-1 gap-gutter md:grid-cols-3">
          {products.map((product) => (
            <article
              key={product.title}
              className="glass-card hover-lift group flex flex-col items-start rounded-lg p-10 text-left"
            >
              <div className="mb-8 flex size-16 items-center justify-center rounded-2xl bg-surface-container transition-colors duration-300 group-hover:bg-primary">
                <Icon
                  name={product.icon}
                  filled
                  className="text-[36px] text-primary group-hover:text-white"
                />
              </div>
              <h3 className="mb-3 text-headline-md text-primary">
                {product.title}
              </h3>
              <p className="mb-8 flex-grow text-body-md text-on-surface-variant">
                {product.body}
              </p>
              <ul className="mb-8 space-y-3 font-label text-on-surface-variant">
                {product.points.map((point) => (
                  <li key={point} className="flex items-center gap-2">
                    <Icon name="check_circle" className="text-[18px] text-primary" />
                    {point}
                  </li>
                ))}
              </ul>
              <Button className="w-full rounded-md bg-surface-container-high text-primary hover:bg-primary hover:text-white">
                {product.cta}
              </Button>
            </article>
          ))}
        </div>
      </div>
    </section>
  )
}
