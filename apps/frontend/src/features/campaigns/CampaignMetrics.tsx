import { useEffect, useState } from 'react'
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Card } from '../../components/ui/Card'
import { api, type LeadsKpis } from '../../lib/api'

// Mismos tonos semánticos que Chip.tsx (hot/warm/cold) pero en hex real —
// recharts pinta con color, no con clases de Tailwind. Tomados del theme
// (@theme en index.css): --color-error, --color-secondary-fixed-dim, --color-outline.
const INTENT_COLOR: Record<string, string> = {
  CALIENTE: '#ba1a1a',
  TIBIO: '#fbbc00',
  FRIO: '#72796f',
}
const INTENT_LABEL: Record<string, string> = {
  CALIENTE: 'Caliente',
  TIBIO: 'Tibio',
  FRIO: 'Frío',
}

export function CampaignMetrics() {
  const [kpis, setKpis] = useState<LeadsKpis | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    let alive = true
    api
      .leadsKpis()
      .then((k) => alive && setKpis(k))
      .catch(() => alive && setError(true))
    return () => {
      alive = false
    }
  }, [])

  if (error) {
    return (
      <Card className="p-5 text-sm text-on-surface-variant">
        No se pudieron cargar las métricas de segmentos ahora mismo.
      </Card>
    )
  }
  if (!kpis) {
    return <Card className="p-5 text-sm text-on-surface-variant">Cargando métricas…</Card>
  }

  const data = kpis.intentDistribution.map((d) => ({
    intent: d.intent,
    label: INTENT_LABEL[d.intent] ?? d.intent,
    count: d.count,
  }))
  const total = data.reduce((sum, d) => sum + d.count, 0)

  return (
    <Card className="flex flex-col gap-3 p-5">
      <h3 className="text-title-md font-bold text-on-surface">Leads por segmento</h3>
      <p className="text-sm text-on-surface-variant">
        {total} lead{total === 1 ? '' : 's'} abiertos · frío/tibio/caliente
      </p>
      <div className="h-52 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <XAxis dataKey="label" tick={{ fontSize: 12 }} />
            <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
            <Tooltip />
            <Bar dataKey="count" radius={[6, 6, 0, 0]}>
              {data.map((d) => (
                <Cell key={d.intent} fill={INTENT_COLOR[d.intent] ?? '#72796f'} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  )
}
