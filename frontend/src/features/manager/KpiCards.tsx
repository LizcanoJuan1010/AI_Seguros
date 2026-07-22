import { Icon } from '../../components/ui/Icon'
import { Card } from '../../components/ui/Card'
import type { Kpi } from '../../data/mock/types'

type Props = {
  items: Kpi[]
}

export function KpiCards({ items }: Props) {
  return (
    <section className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
      {items.map((kpi) => (
        <Card key={kpi.id} className="rounded-lg border border-outline-variant p-5">
          <div className="mb-2 flex items-start justify-between">
            <p className="text-sm font-medium text-on-surface-variant">
              {kpi.label}
            </p>
            <Icon
              name={kpi.icon}
              className="rounded-lg bg-primary/10 p-1.5 text-primary"
            />
          </div>
          <div className="flex items-baseline gap-2">
            <h3 className="text-2xl font-bold text-on-surface">{kpi.value}</h3>
            <span
              className={`flex items-center text-xs font-bold ${
                kpi.deltaUp ? 'text-green-700' : 'text-error'
              }`}
            >
              <Icon
                name={kpi.deltaUp ? 'trending_up' : 'trending_down'}
                className="text-xs"
              />
              {kpi.delta}
            </span>
          </div>
          <p className="mt-1 text-[10px] text-outline">{kpi.hint}</p>
        </Card>
      ))}
    </section>
  )
}
