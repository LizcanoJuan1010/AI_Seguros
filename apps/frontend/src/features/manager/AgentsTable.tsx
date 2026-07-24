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
      {/* Móvil (<md): cada agente como tarjeta apilada */}
      <div className="flex flex-col gap-3 p-4 md:hidden">
        {agents.map((agent) => (
          <div
            key={agent.id}
            className="rounded-xl border border-outline-variant bg-surface-container-lowest p-4"
          >
            <div className="flex items-center justify-between gap-3">
              <div className="flex min-w-0 items-center gap-3">
                {agent.avatar ? (
                  <img
                    src={agent.avatar}
                    alt={agent.name}
                    className="size-9 shrink-0 rounded-full border-2 border-primary/20 object-cover"
                  />
                ) : (
                  <span className="flex size-9 shrink-0 items-center justify-center rounded-full border-2 border-primary/20 bg-primary-container text-xs font-bold text-on-primary-container">
                    {agent.name
                      .split(' ')
                      .slice(0, 2)
                      .map((w) => w[0])
                      .join('')}
                  </span>
                )}
                <div className="min-w-0">
                  <p className="truncate text-sm font-bold text-on-surface">
                    {agent.name}
                  </p>
                  <p className="text-[10px] text-on-surface-variant">
                    {agent.role}
                  </p>
                </div>
              </div>
              <Chip tone={agent.conversionTone === 'good' ? 'success' : 'amber'}>
                {agent.conversion}
              </Chip>
            </div>
            <div className="mt-3 flex items-center justify-between gap-3">
              <div className="grid flex-1 grid-cols-3 gap-2 text-center">
                {[
                  { label: 'Leads', value: agent.leads },
                  { label: 'Llamadas', value: agent.calls },
                  { label: 'Cierres', value: agent.closes, bold: true },
                ].map((s) => (
                  <div
                    key={s.label}
                    className="rounded-lg bg-surface-container-low/60 py-2"
                  >
                    <p
                      className={`text-sm text-on-surface ${s.bold ? 'font-bold' : ''}`}
                    >
                      {s.value}
                    </p>
                    <p className="text-[10px] tracking-wide text-on-surface-variant uppercase">
                      {s.label}
                    </p>
                  </div>
                ))}
              </div>
              <svg
                className={`h-8 w-14 shrink-0 ${agent.sparkTone === 'up' ? 'text-green-600' : 'text-error'}`}
                viewBox="0 0 100 40"
                aria-label="Tendencia"
              >
                <polyline
                  fill="none"
                  points={agent.spark}
                  stroke="currentColor"
                  strokeWidth="2"
                />
              </svg>
            </div>
          </div>
        ))}
      </div>

      {/* Desktop (md+): tabla */}
      <div className="hidden overflow-x-auto md:block">
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
