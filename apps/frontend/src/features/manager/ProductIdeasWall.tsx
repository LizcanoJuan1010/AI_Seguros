/**
 * Muro de ideas de producto (pestaña Resumen del gerente): demanda que los
 * clientes expresan en las conversaciones y que el catálogo NO cubre hoy,
 * con viabilidad explicada (GET /api/insights/product-ideas del servicio IA).
 * Requiere sesión de gerente (JWT); si no hay permiso o no hay ideas, no se
 * muestra nada.
 */
import { useEffect, useState } from 'react'
import { Card } from '../../components/ui/Card'
import { Icon } from '../../components/ui/Icon'
import { authHeaders } from '../../lib/authFetch'
import { useTenant } from '../../tenant/TenantContext'
import { AiChatModal } from './AiChatModal'

type ProductIdea = {
  tema: string
  titulo: string
  descripcion: string
  menciones: number
  solicitantes: number
  ejemplos: string[]
  viabilidad: 'alta' | 'media' | 'baja'
  razon_viabilidad: string
}

type IdeasResponse = {
  ideas: ProductIdea[]
  mensajes_analizados: number
  generado_por: string
}

const VIABILIDAD_META: Record<
  ProductIdea['viabilidad'],
  { label: string; chip: string; border: string }
> = {
  alta: {
    label: 'Viabilidad alta',
    chip: 'bg-primary/10 text-primary',
    border: 'border-primary/40',
  },
  media: {
    label: 'Viabilidad media',
    chip: 'bg-amber-cta/20 text-on-secondary-fixed-variant',
    border: 'border-amber-cta/50',
  },
  baja: {
    label: 'Viabilidad baja',
    chip: 'bg-surface-variant text-outline',
    border: 'border-outline-variant',
  },
}

export function ProductIdeasWall() {
  const { teamId } = useTenant()
  const [data, setData] = useState<IdeasResponse | null>(null)
  const [active, setActive] = useState<ProductIdea | null>(null)

  useEffect(() => {
    let alive = true
    fetch('/api/insights/product-ideas', { headers: authHeaders() })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d: IdeasResponse) => alive && setData(d))
      .catch(() => alive && setData(null))
    return () => {
      alive = false
    }
  }, [teamId])

  if (!data || data.ideas.length === 0) return null

  const promptFor = (idea: ProductIdea) =>
    `Como analista de negocio de una aseguradora, evalúa la viabilidad de lanzar un nuevo producto: "${idea.titulo}" (${idea.descripcion}). ` +
    `Demanda detectada en conversaciones reales: ${idea.menciones} menciones de ${idea.solicitantes} clientes distintos. ` +
    `Ejemplos textuales de clientes: ${idea.ejemplos.map((e) => `"${e}"`).join(' ')}. ` +
    `Contexto de viabilidad: ${idea.razon_viabilidad}. ` +
    `Da un veredicto claro (¿vale la pena?), riesgos, y 3 recomendaciones accionables para el negocio. Usa datos del negocio si te ayudan.`

  return (
    <Card className="rounded-lg border border-outline-variant p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-bold text-on-surface">
            <Icon name="lightbulb" className="text-amber-cta" />
            Ideas de producto que piden los clientes
          </h2>
          <p className="text-xs text-on-surface-variant">
            Demanda detectada en {data.mensajes_analizados} mensajes de clientes
            que el catálogo actual no cubre
          </p>
        </div>
        <span className="rounded-full bg-primary/10 px-2.5 py-1 text-[11px] font-bold text-primary">
          {data.ideas.length} oportunidad(es)
        </span>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {data.ideas.map((idea) => {
          const meta = VIABILIDAD_META[idea.viabilidad]
          return (
            <article
              key={idea.tema}
              className={`flex flex-col gap-2 rounded-xl border-2 ${meta.border} bg-surface-container-lowest p-4`}
            >
              <div className="flex items-start justify-between gap-2">
                <h3 className="text-sm font-bold text-on-surface">{idea.titulo}</h3>
                <span
                  className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${meta.chip}`}
                >
                  {meta.label}
                </span>
              </div>
              <p className="text-xs text-on-surface-variant">{idea.descripcion}</p>
              <p className="flex items-center gap-1 text-xs font-semibold text-on-surface">
                <Icon name="record_voice_over" className="text-[14px] text-primary" />
                {idea.menciones} mención(es) · {idea.solicitantes} cliente(s)
              </p>
              {idea.ejemplos[0] && (
                <blockquote className="border-l-2 border-primary/40 pl-2 text-[11px] text-outline italic">
                  “{idea.ejemplos[0]}”
                </blockquote>
              )}
              <p className="rounded-lg bg-surface-container-low p-2 text-[10px] leading-snug text-on-surface-variant">
                <span className="font-bold">¿Por qué? </span>
                {idea.razon_viabilidad}
              </p>
              <button
                type="button"
                onClick={() => setActive(idea)}
                className="mt-auto flex items-center justify-center gap-1.5 rounded-lg border border-primary/30 bg-primary/5 py-2 text-xs font-bold text-primary transition-colors hover:bg-primary/10"
              >
                <Icon name="smart_toy" className="text-[16px]" />
                Analizar con IA
              </button>
            </article>
          )
        })}
      </div>

      <AiChatModal
        open={active != null}
        onClose={() => setActive(null)}
        title={active ? active.titulo : ''}
        subtitle="Análisis de viabilidad por la IA"
        initialPrompt={active ? promptFor(active) : ''}
      />
    </Card>
  )
}
