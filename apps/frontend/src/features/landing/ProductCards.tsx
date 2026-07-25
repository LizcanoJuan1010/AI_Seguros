import { Link } from 'react-router-dom'
import { Icon } from '../../components/ui/Icon'
import { Reveal } from '../../components/ui/Reveal'

const products = [
  {
    icon: 'favorite',
    title: 'Seguro de Vida',
    body: 'Asegura el bienestar de los que más amas con una póliza flexible que crece con tu familia.',
    points: ['Cobertura global', 'Sin exámenes tediosos'],
    cta: 'Cotizar Vida',
    prompt:
      'Quiero cotizar un seguro de vida. Hazme una por una las preguntas que necesites (edad, si fumo, cobertura que busco) y dame una cotización real.',
  },
  {
    icon: 'directions_car',
    title: 'Seguro de Auto',
    body: 'Protección total en la vía con asistencia IA inmediata para accidentes y grúas.',
    points: ['Asistencia 24/7', 'Chofer de reemplazo'],
    cta: 'Cotizar Auto',
    prompt:
      'Quiero cotizar un seguro de auto. Pregúntame una por una los datos de mi carro (marca, modelo, año, ciudad) y dame una cotización real.',
  },
  {
    icon: 'health_and_safety',
    title: 'Seguro de Salud',
    body: 'Acceso a las mejores clínicas y especialistas con reembolso asistido por inteligencia artificial.',
    points: ['Telemedicina incluida', 'Amplia red nacional'],
    cta: 'Cotizar Salud',
    prompt:
      'Quiero cotizar un seguro de salud. Hazme una por una las preguntas que necesites (edad, ciudad, cobertura que busco) y dame una cotización real.',
  },
]

export function ProductCards() {
  return (
    <section
      id="planes"
      className="bg-mist-white px-margin-mobile py-24 md:px-margin-desktop"
    >
      <div className="mx-auto max-w-container-max">
        <Reveal className="mb-16 flex flex-col items-end justify-between gap-6 md:flex-row">
          <div className="max-w-xl">
            <p className="mb-2 font-hand text-xl font-semibold text-secondary">
              Nuestros ramos
            </p>
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
        </Reveal>
        <div id="ramos" className="grid grid-cols-1 gap-gutter md:grid-cols-3">
          {products.map((product, i) => (
            <Reveal key={product.title} delay={i * 140} className="h-full">
            <article
              className="glass-card hover-lift group flex h-full flex-col items-start rounded-lg p-10 text-left"
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
              <Link
                to={`/asistente?q=${encodeURIComponent(product.prompt)}`}
                className="inline-flex w-full items-center justify-center gap-2 rounded-md bg-surface-container-high px-4 py-2.5 text-label-md text-primary transition-all hover:bg-primary hover:text-white"
              >
                {product.cta}
                <Icon name="arrow_forward" className="text-[18px]" />
              </Link>
            </article>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  )
}
