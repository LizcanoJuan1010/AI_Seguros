import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Icon } from '../../components/ui/Icon'
import { Reveal } from '../../components/ui/Reveal'
import {
  FEATURE_CATEGORIES,
  featureCards,
  featureHref,
  type FeatureCard,
  type FeatureCategory,
} from './featureCatalog'

/**
 * Showcase interactivo de TODO lo que hace la plataforma, en formato carrusel:
 * una sola fila deslizable (rueda, swipe o arrastre con el cursor) con snap
 * por tarjeta. Cada card lanza la pregunta exacta en `/asistente?q=...` (el
 * chat la auto-envía y la IA ejecuta la herramienta real) o abre la
 * experiencia completa (llamada, dashboards…).
 */

function QuestionChip({ prompt, featured }: { prompt: string; featured?: boolean }) {
  if (featured) {
    return (
      <span className="inline-flex max-w-full items-center gap-2 self-start rounded-full bg-amber-cta px-4 py-2 text-label-md font-bold text-primary shadow-md shadow-amber-cta/25 transition-transform duration-300 group-hover:scale-[1.03]">
        <Icon name="bolt" filled className="shrink-0 text-[18px]" />
        <span className="truncate">“{prompt}”</span>
      </span>
    )
  }
  return (
    <span className="inline-flex max-w-full items-center gap-1.5 self-start rounded-full border border-amber-cta/50 bg-amber-cta/15 px-3.5 py-1.5 text-label-sm font-semibold text-on-secondary-fixed-variant transition-all group-hover:border-amber-cta group-hover:bg-amber-cta/25">
      <Icon name="bolt" filled className="shrink-0 text-[15px] text-secondary" />
      <span className="truncate">“{prompt}”</span>
    </span>
  )
}

function ManagerBadge() {
  return (
    <span className="inline-flex shrink-0 items-center gap-1 rounded-full border border-secondary/30 bg-secondary/10 px-2.5 py-1 text-label-sm font-semibold text-secondary">
      <Icon name="admin_panel_settings" filled className="text-[14px]" />
      Modo gerente
    </span>
  )
}

function DemoBadge() {
  return (
    <span className="inline-flex shrink-0 items-center gap-1 rounded-full border border-primary/20 bg-primary/10 px-2.5 py-1 text-label-sm font-semibold text-primary">
      <Icon name="play_circle" filled className="text-[14px]" />
      Demo en vivo
    </span>
  )
}

function ShowcaseCard({ card }: { card: FeatureCard }) {
  if (card.featured && card.prompt) {
    return (
      <div className="carousel-item w-[88vw] max-w-[520px] shrink-0 snap-start sm:w-[480px]">
        <Link
          to={featureHref(card)}
          draggable={false}
          className="group flex h-full w-full flex-col rounded-2xl bg-primary p-6 text-left shadow-lg shadow-primary/30 transition-transform duration-300 hover:-translate-y-1 md:p-7"
        >
          <div className="mb-5 flex items-start justify-between gap-3">
            <span className="flex size-14 shrink-0 items-center justify-center rounded-2xl bg-white/10 transition-colors duration-300 group-hover:bg-amber-cta/20">
              <Icon name={card.icon} filled className="text-[30px] text-amber-cta" />
            </span>
            <span className="inline-flex shrink-0 items-center gap-1 rounded-full border border-amber-cta/40 bg-amber-cta/15 px-2.5 py-1 text-label-sm font-semibold text-amber-cta">
              <Icon name="bolt" filled className="text-[14px]" />
              La más pedida
            </span>
          </div>
          <h3 className="mb-2 text-headline-md text-white">{card.title}</h3>
          <p className="mb-6 flex-grow text-body-md text-white/75">{card.desc}</p>
          <QuestionChip prompt={card.prompt} featured />
        </Link>
      </div>
    )
  }

  return (
    <div className="carousel-item w-[82vw] max-w-[400px] shrink-0 snap-start sm:w-[340px]">
      <Link
        to={featureHref(card)}
        draggable={false}
        className="glass-card group flex h-full w-full flex-col rounded-2xl p-6 text-left transition-transform duration-300 hover:-translate-y-1"
      >
        <div className="mb-5 flex items-start justify-between gap-3">
          <span className="flex size-12 shrink-0 items-center justify-center rounded-xl bg-primary/10 transition-colors duration-300 group-hover:bg-primary">
            <Icon
              name={card.icon}
              filled
              className="text-[26px] text-primary transition-colors duration-300 group-hover:text-white"
            />
          </span>
          {card.managerMode && <ManagerBadge />}
          {card.to && <DemoBadge />}
        </div>
        <h3 className="mb-2 text-body-lg font-bold text-on-surface">{card.title}</h3>
        <p className="mb-6 flex-grow text-body-md text-on-surface-variant">
          {card.desc}
        </p>
        {card.prompt ? (
          <QuestionChip prompt={card.prompt} />
        ) : (
          <span className="inline-flex items-center gap-1.5 self-start text-label-md font-bold text-primary">
            Abrir demo
            <Icon
              name="arrow_forward"
              className="text-[18px] transition-transform group-hover:translate-x-0.5"
            />
          </span>
        )}
      </Link>
    </div>
  )
}

export function FeatureShowcase() {
  const [active, setActive] = useState<FeatureCategory | 'todos'>('todos')
  const [canPrev, setCanPrev] = useState(false)
  const [canNext, setCanNext] = useState(true)
  const [progress, setProgress] = useState(0)
  const trackRef = useRef<HTMLDivElement>(null)
  // Arrastre con cursor (desktop): en touch el scroll nativo ya funciona.
  const dragRef = useRef({ down: false, moved: false, startX: 0, startLeft: 0 })

  const visible =
    active === 'todos'
      ? featureCards
      : featureCards.filter((c) => c.category === active)

  const updateArrows = () => {
    const el = trackRef.current
    if (!el) return
    const max = el.scrollWidth - el.clientWidth
    setCanPrev(el.scrollLeft > 8)
    setCanNext(el.scrollLeft < max - 8)
    setProgress(max > 0 ? el.scrollLeft / max : 0)
  }

  useEffect(() => {
    trackRef.current?.scrollTo({ left: 0, behavior: 'instant' })
    updateArrows()
  }, [active])

  useEffect(() => {
    window.addEventListener('resize', updateArrows)
    return () => window.removeEventListener('resize', updateArrows)
  }, [])

  const page = (dir: -1 | 1) => {
    const el = trackRef.current
    if (!el) return
    el.scrollBy({ left: dir * Math.max(el.clientWidth * 0.85, 320), behavior: 'smooth' })
  }

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.pointerType !== 'mouse') return
    const el = trackRef.current
    if (!el) return
    dragRef.current = {
      down: true,
      moved: false,
      startX: e.clientX,
      startLeft: el.scrollLeft,
    }
  }

  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current
    const el = trackRef.current
    if (!drag.down || !el) return
    const dx = e.clientX - drag.startX
    if (!drag.moved && Math.abs(dx) > 6) {
      drag.moved = true
      // Capturar el puntero SOLO al arrastrar de verdad: si se captura desde
      // pointerdown, el click resultante se retargetea al track y las cards
      // dejan de navegar. Sin snap durante el gesto; al soltar re-encaja.
      el.style.scrollSnapType = 'none'
      el.setPointerCapture(e.pointerId)
    }
    if (drag.moved) el.scrollLeft = drag.startLeft - dx
  }

  const endDrag = () => {
    const el = trackRef.current
    dragRef.current.down = false
    if (el) el.style.scrollSnapType = ''
  }

  // Si hubo arrastre, el click que lo cierra no debe navegar a la card.
  const onClickCapture = (e: React.MouseEvent<HTMLDivElement>) => {
    if (dragRef.current.moved) {
      e.preventDefault()
      e.stopPropagation()
      dragRef.current.moved = false
    }
  }

  return (
    <section
      id="funciones"
      className="px-margin-mobile py-24 md:px-margin-desktop"
    >
      <div className="mx-auto max-w-container-max">
        <Reveal className="mb-10 flex flex-col justify-between gap-6 md:flex-row md:items-end">
          <div className="max-w-2xl">
            <p className="mb-2 font-hand text-xl font-semibold text-secondary">
              Pruébalo en vivo
            </p>
            <h2 className="mb-4 text-headline-lg text-primary">
              Todo lo que la IA hace por ti, a un clic
            </h2>
            <p className="text-body-md text-on-surface-variant">
              Cada tarjeta lanza la pregunta exacta en el chat y la asesora
              ejecuta la función real: cotiza, emite tu póliza, cobra, atiende
              siniestros y te muestra el negocio. Desliza y tócala.
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-3">
            <span className="hidden text-label-sm text-on-surface-variant sm:block">
              {visible.length} funciones
            </span>
            <button
              type="button"
              aria-label="Anteriores"
              disabled={!canPrev}
              onClick={() => page(-1)}
              className="flex size-11 items-center justify-center rounded-full border border-outline-variant/60 bg-surface-container-lowest/70 text-primary transition-all hover:bg-primary hover:text-white disabled:pointer-events-none disabled:opacity-35"
            >
              <Icon name="arrow_back" className="text-[20px]" />
            </button>
            <button
              type="button"
              aria-label="Siguientes"
              disabled={!canNext}
              onClick={() => page(1)}
              className="flex size-11 items-center justify-center rounded-full border border-outline-variant/60 bg-surface-container-lowest/70 text-primary transition-all hover:bg-primary hover:text-white disabled:pointer-events-none disabled:opacity-35"
            >
              <Icon name="arrow_forward" className="text-[20px]" />
            </button>
          </div>
        </Reveal>

        <Reveal className="mb-8">
          <div
            className="flex flex-wrap gap-2"
            aria-label="Filtrar funciones por categoría"
          >
            {FEATURE_CATEGORIES.map((cat) => {
              const isActive = active === cat.id
              return (
                <button
                  key={cat.id}
                  type="button"
                  aria-pressed={isActive}
                  onClick={() => setActive(cat.id)}
                  className={`inline-flex items-center gap-1.5 rounded-full border px-4 py-2 text-label-md transition-colors duration-200 ${
                    isActive
                      ? 'border-transparent bg-primary text-on-primary shadow-md shadow-primary/25'
                      : 'border-outline-variant/60 bg-surface-container-lowest/70 text-on-surface-variant hover:bg-primary/10 hover:text-primary'
                  }`}
                >
                  <Icon name={cat.icon} filled={isActive} className="text-[18px]" />
                  {cat.label}
                </button>
              )
            })}
          </div>
        </Reveal>

        <Reveal>
          <div
            ref={trackRef}
            onScroll={updateArrows}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={endDrag}
            onPointerCancel={endDrag}
            onClickCapture={onClickCapture}
            className={`flex cursor-grab select-none snap-x snap-mandatory items-stretch gap-4 overflow-x-auto scroll-px-1 px-1 pb-4 pt-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden active:cursor-grabbing md:gap-5 ${
              canPrev && canNext
                ? 'carousel-mask-both'
                : canNext
                  ? 'carousel-mask-right'
                  : canPrev
                    ? 'carousel-mask-left'
                    : ''
            }`}
          >
            {visible.map((card) => (
              <ShowcaseCard key={card.id} card={card} />
            ))}
          </div>
          {(canPrev || canNext) && (
            <div
              className="mx-auto mt-2 h-1 w-40 overflow-hidden rounded-full bg-primary/10 md:w-56"
              aria-hidden
            >
              <div
                className="h-full rounded-full bg-primary/70 transition-[width] duration-200 ease-out"
                style={{ width: `${Math.max(8, Math.round(progress * 100))}%` }}
              />
            </div>
          )}
        </Reveal>
      </div>
    </section>
  )
}
