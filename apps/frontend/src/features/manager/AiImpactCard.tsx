import { Card } from '../../components/ui/Card'
import { CountUp } from '../../components/ui/CountUp'
import { Icon } from '../../components/ui/Icon'
import type { AiImpact } from '../../lib/api'

type Props = {
  data: AiImpact | null
}

type Stat = {
  id: string
  label: string
  value: number | null
  suffix: string
  decimals: number
  hint: string
  icon: string
}

function toStats(d: AiImpact | null): Stat[] {
  return [
    {
      id: 'quote-speed',
      label: 'Cotización promedio',
      value: d?.avgQuoteMinutes ?? null,
      suffix: ' min',
      decimals: 1,
      hint: 'De "hola" a prima cotizada',
      icon: 'bolt',
    },
    {
      id: 'auto-emission',
      label: 'Pólizas sin humano',
      value: d?.autoEmissionPct ?? null,
      suffix: '%',
      decimals: 0,
      hint: `Emisión autónoma (${d?.policiesTotal ?? 0} pólizas)`,
      icon: 'smart_toy',
    },
    {
      id: 'conversion',
      label: 'Conversión lead → venta',
      value: d?.conversionPct ?? null,
      suffix: '%',
      decimals: 1,
      hint: 'Funnel conversacional',
      icon: 'trending_up',
    },
    {
      id: 'close-speed',
      label: 'Cierre promedio',
      value: d?.avgCloseDays ?? null,
      suffix: ' días',
      decimals: 1,
      hint:
        d?.claimsCycleDays != null
          ? `Reclamos resueltos en ${d.claimsCycleDays.toLocaleString('es-CO', { maximumFractionDigits: 1 })} días`
          : 'Del primer contacto a la póliza',
      icon: 'timer',
    },
  ]
}

/** Métricas de impacto de la IA en el negocio (velocidad, autonomía, conversión). */
export function AiImpactCard({ data }: Props) {
  const stats = toStats(data)
  return (
    <Card className="rounded-lg border border-outline-variant p-5">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-label-md font-bold uppercase tracking-wide text-on-surface-variant">
            Impacto IA
          </h2>
          <p className="text-xs text-outline">
            Lo que la automatización le ahorra al negocio
          </p>
        </div>
        <Icon
          name="auto_awesome"
          className="rounded-lg bg-amber-cta/20 p-1.5 text-primary"
        />
      </div>
      <div className="grid grid-cols-1 gap-4 xs:grid-cols-2 lg:grid-cols-4">
        {stats.map((s) => (
          <div key={s.id} className="flex flex-col gap-1">
            <span className="flex items-center gap-1 text-xs font-medium text-on-surface-variant">
              <Icon name={s.icon} className="text-sm text-primary" />
              {s.label}
            </span>
            <span className="text-2xl font-bold text-on-surface">
              {s.value != null ? (
                <CountUp end={s.value} decimals={s.decimals} suffix={s.suffix} />
              ) : (
                '—'
              )}
            </span>
            <span className="text-[10px] text-outline">{s.hint}</span>
          </div>
        ))}
      </div>
    </Card>
  )
}
