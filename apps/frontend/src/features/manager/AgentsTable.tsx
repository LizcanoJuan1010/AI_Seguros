import { Card } from '../../components/ui/Card'
import { Chip } from '../../components/ui/Chip'
import { Icon } from '../../components/ui/Icon'
import type { AgentRow } from '../../data/mock/types'

type Props = {
  agents: AgentRow[]
}

export function AgentsTable({ agents }: Props) {
  return (
    <Card className="flex flex-grow flex-col rounded-lg border border-outline-variant">
      <div className="flex items-center justify-between border-b border-outline-variant p-5">
        <h2 className="text-lg font-bold text-on-surface">
          Rendimiento de Agentes
        </h2>
        <button
          type="button"
          className="flex items-center gap-1 text-sm font-semibold text-primary hover:underline"
        >
          Ver todos <Icon name="chevron_right" className="text-sm" />
        </button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left">
          <thead>
            <tr className="bg-surface-container-low/50">
              {['Agente', 'Leads', 'Llamadas', 'Cierres', 'Conv %', 'Tendencia'].map(
                (h) => (
                  <th
                    key={h}
                    className="px-5 py-3 text-xs font-semibold tracking-wider text-on-surface-variant uppercase"
                  >
                    {h}
                  </th>
                ),
              )}
            </tr>
          </thead>
          <tbody className="divide-y divide-outline-variant">
            {agents.map((agent) => (
              <tr key={agent.id} className="transition-colors hover:bg-mist-white">
                <td className="px-5 py-4 whitespace-nowrap">
                  <div className="flex items-center gap-3">
                    {agent.avatar ? (
                      <img
                        src={agent.avatar}
                        alt={agent.name}
                        className="size-9 rounded-full border-2 border-primary/20 object-cover"
                      />
                    ) : (
                      <span className="flex size-9 items-center justify-center rounded-full border-2 border-primary/20 bg-primary-container text-xs font-bold text-on-primary-container">
                        {agent.name
                          .split(' ')
                          .slice(0, 2)
                          .map((w) => w[0])
                          .join('')}
                      </span>
                    )}
                    <div>
                      <p className="text-sm font-bold text-on-surface">
                        {agent.name}
                      </p>
                      <p className="text-[10px] text-on-surface-variant">
                        {agent.role}
                      </p>
                    </div>
                  </div>
                </td>
                <td className="px-5 py-4 text-sm">{agent.leads}</td>
                <td className="px-5 py-4 text-sm">{agent.calls}</td>
                <td className="px-5 py-4 text-sm font-bold">{agent.closes}</td>
                <td className="px-5 py-4">
                  <Chip
                    tone={agent.conversionTone === 'good' ? 'success' : 'amber'}
                  >
                    {agent.conversion}
                  </Chip>
                </td>
                <td className="px-5 py-4">
                  <svg
                    className={`h-8 w-16 ${agent.sparkTone === 'up' ? 'text-green-600' : 'text-error'}`}
                    viewBox="0 0 100 40"
                  >
                    <polyline
                      fill="none"
                      points={agent.spark}
                      stroke="currentColor"
                      strokeWidth="2"
                    />
                  </svg>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}
