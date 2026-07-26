import { Icon } from '../../components/ui/Icon'
import { Button } from '../../components/ui/Button'
import type { Alert } from '../../data/mock/types'

type Props = {
  items: Alert[]
}

export function AlertsPanel({ items }: Props) {
  return (
    <div className="overflow-hidden rounded-lg border-2 border-amber-cta bg-white shadow-sm">
      <div className="flex items-center gap-2 bg-amber-cta px-4 py-3">
        <Icon name="warning" className="animate-pulse text-on-secondary-fixed" />
        <h3 className="text-sm font-bold text-on-secondary-fixed">
          Alertas Críticas
        </h3>
        <span className="ml-auto rounded-full bg-on-secondary-fixed/15 px-2 py-0.5 text-[11px] font-bold text-on-secondary-fixed">
          {items.length}
        </span>
      </div>
      {/* Ancho completo: las alertas se reparten en columnas para llenar la
          caja en vez de apilarse en una sola tira larga. */}
      <div className="grid grid-cols-1 gap-3 p-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
        {items.map((alert) => (
          <div
            key={alert.id}
            className={`flex flex-col rounded-lg border-l-4 p-3 ${
              alert.tone === 'amber'
                ? 'border-amber-cta bg-amber-50'
                : 'border-error bg-error-container/40'
            }`}
          >
            <p
              className={`mb-1 text-xs font-bold ${
                alert.tone === 'amber'
                  ? 'text-on-secondary-fixed-variant'
                  : 'text-on-error-container'
              }`}
            >
              {alert.title}
            </p>
            <p
              className={`text-[11px] ${
                alert.tone === 'amber'
                  ? 'text-on-secondary-fixed-variant'
                  : 'text-on-error-container'
              }`}
            >
              {alert.body}
            </p>
            {alert.cta ? (
              <Button
                variant="cta"
                className="mt-2 w-full rounded-md py-1.5 text-xs"
              >
                {alert.cta}
              </Button>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  )
}
