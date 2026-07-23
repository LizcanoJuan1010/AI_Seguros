import { Icon } from '../../components/ui/Icon'
import { formatCop, type ApiClaim } from '../../lib/api'

type Props = {
  items: ApiClaim[]
}

const STATUS_LABEL: Record<string, { label: string; className: string }> = {
  REPORTADO: { label: 'Reportado', className: 'bg-primary/10 text-primary' },
  EN_REVISION: {
    label: 'En revisión',
    className: 'bg-amber-cta/20 text-on-secondary-fixed-variant',
  },
  DOCS_PENDIENTES: {
    label: 'Docs pendientes',
    className: 'bg-amber-cta/20 text-on-secondary-fixed-variant',
  },
  APROBADO: { label: 'Aprobado', className: 'bg-primary/10 text-primary' },
  PAGADO: { label: 'Pagado', className: 'bg-primary/10 text-primary' },
  RECHAZADO: {
    label: 'Rechazado',
    className: 'bg-error-container/50 text-on-error-container',
  },
}

/** Reclamos del equipo con su score de fraude (triage del servicio IA). */
export function ClaimsPanel({ items }: Props) {
  return (
    <div className="overflow-hidden rounded-lg border border-outline-variant bg-white shadow-sm">
      <div className="flex items-center gap-2 bg-primary px-4 py-3">
        <Icon name="health_and_safety" className="text-on-primary" />
        <h3 className="text-sm font-bold text-on-primary">Reclamos</h3>
        <span className="ml-auto rounded-full bg-on-primary/15 px-2 py-0.5 text-[11px] font-bold text-on-primary">
          {items.length}
        </span>
      </div>
      <div className="flex flex-col gap-3 p-4">
        {items.map((claim) => {
          const status =
            STATUS_LABEL[claim.status] ?? STATUS_LABEL.REPORTADO
          const fraud = Number(claim.fraudScore ?? 0)
          const flags = claim.fraudFlags ?? []
          return (
            <div
              key={claim.id}
              className="rounded-lg border border-outline-variant/60 p-3"
            >
              <div className="mb-1 flex items-center justify-between gap-2">
                <p className="font-mono text-xs font-bold text-on-surface">
                  {claim.claimNumber}
                </p>
                <span
                  className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${status.className}`}
                >
                  {status.label}
                </span>
              </div>
              <p className="text-[11px] text-on-surface-variant">
                {claim.insuranceType ?? '—'}
                {claim.amountEstimateCop
                  ? ` · Estimado ${formatCop(claim.amountEstimateCop)}`
                  : ''}
              </p>
              {claim.description ? (
                <p className="mt-1 line-clamp-2 text-[11px] text-outline">
                  {claim.description}
                </p>
              ) : null}
              {fraud >= 0.5 ? (
                <div className="mt-2 rounded-md border-l-4 border-error bg-error-container/40 p-2">
                  <p className="flex items-center gap-1 text-[11px] font-bold text-on-error-container">
                    <Icon name="report" filled className="text-[13px]" />
                    Posible fraude · score {fraud.toFixed(2)}
                  </p>
                  {flags.slice(0, 3).map((f) => (
                    <p
                      key={f}
                      className="mt-0.5 text-[10px] text-on-error-container"
                    >
                      {f}
                    </p>
                  ))}
                </div>
              ) : null}
            </div>
          )
        })}
      </div>
    </div>
  )
}
