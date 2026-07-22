import { Icon } from '../../components/ui/Icon'
import { Chip } from '../../components/ui/Chip'
import { Button } from '../../components/ui/Button'
import type { Lead } from '../../data/mock/types'

type Props = {
  leads: Lead[]
  onSelect: (id: string) => void
}

const intentTone = {
  hot: 'hot',
  warm: 'warm',
  cold: 'cold',
} as const

export function LeadsTable({ leads, onSelect }: Props) {
  return (
    <div className="flex-1 overflow-auto bg-surface-container-low px-8 py-6">
      <div className="overflow-hidden rounded-2xl border border-outline-variant bg-surface-container-lowest shadow-sm">
        <table className="w-full border-collapse text-left">
          <thead className="border-b border-outline-variant bg-surface-container-high">
            <tr>
              {[
                'Nombre del Cliente',
                'Tipo',
                'Resumen IA',
                'Intención',
                'Prima (COP)',
                'Acción',
              ].map((h) => (
                <th
                  key={h}
                  className="px-6 py-4 text-xs font-bold tracking-wider text-outline uppercase"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-outline-variant">
            {leads.map((lead) => (
              <tr
                key={lead.id}
                className="cursor-pointer transition-colors hover:bg-surface-container-low"
                onClick={() => onSelect(lead.id)}
              >
                <td className="px-6 py-4">
                  <div className="flex items-center gap-3">
                    <div className="flex size-8 items-center justify-center rounded-full bg-primary-fixed text-xs font-bold text-primary uppercase">
                      {lead.initials}
                    </div>
                    <div>
                      <p className="text-sm font-bold text-on-surface">
                        {lead.name}
                      </p>
                      <p className="text-xs text-outline">{lead.when}</p>
                    </div>
                  </div>
                </td>
                <td className="px-6 py-4">
                  <span className="flex items-center gap-1.5 rounded-md bg-primary-fixed/40 px-2 py-1 text-xs font-semibold text-primary">
                    <Icon name={lead.typeIcon} className="text-sm" />
                    {lead.type}
                  </span>
                </td>
                <td className="px-6 py-4">
                  <p className="line-clamp-1 text-sm text-on-surface-variant">
                    {lead.summary}
                  </p>
                </td>
                <td className="px-6 py-4">
                  <Chip tone={intentTone[lead.intent]}>
                    <Icon
                      name={
                        lead.intent === 'hot'
                          ? 'local_fire_department'
                          : lead.intent === 'warm'
                            ? 'thermostat'
                            : 'ac_unit'
                      }
                      filled={lead.intent !== 'cold'}
                      className="text-sm"
                    />
                    {lead.intentLabel}
                  </Chip>
                </td>
                <td className="px-6 py-4 font-mono text-sm font-bold">
                  {lead.premium}
                </td>
                <td className="px-6 py-4">
                  <Button
                    className="rounded-md bg-primary-container px-2 py-2 text-on-primary-container"
                    onClick={(e) => {
                      e.stopPropagation()
                      onSelect(lead.id)
                    }}
                  >
                    <Icon name="phone" className="text-base" />
                    <span className="pr-1 text-xs font-bold">Llamar</span>
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
