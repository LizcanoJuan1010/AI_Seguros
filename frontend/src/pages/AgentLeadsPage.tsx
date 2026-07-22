import { useMemo, useState } from 'react'
import { Icon } from '../components/ui/Icon'
import { Button } from '../components/ui/Button'
import { LeadFilters } from '../features/agent/LeadFilters'
import { LeadsTable } from '../features/agent/LeadsTable'
import { LeadDetailDrawer } from '../features/agent/LeadDetailDrawer'
import { leads } from '../data/mock/leads'
import type { LeadStatus } from '../data/mock/types'

export function AgentLeadsPage() {
  const [tab, setTab] = useState<LeadStatus>('todos')
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const filtered = useMemo(() => {
    if (tab === 'todos') return leads
    return leads.filter((lead) => lead.status === tab)
  }, [tab])

  const selected = leads.find((lead) => lead.id === selectedId) ?? null

  return (
    <div className="relative flex h-full min-h-[calc(100svh-4.5rem)] flex-col overflow-hidden">
      <header className="glass-header sticky top-0 z-10 flex h-20 items-center justify-between border-b border-outline-variant px-8">
        <div>
          <h2 className="text-headline-md font-bold text-on-surface">
            Bandeja de Entrada de Leads
          </h2>
          <p className="text-sm font-medium text-outline">
            Leads generados por IA en tiempo real
          </p>
        </div>
        <div className="flex items-center gap-4">
          <div className="relative">
            <Icon
              name="search"
              className="absolute top-1/2 left-3 -translate-y-1/2 text-outline"
            />
            <input
              className="w-64 rounded-lg border-none bg-surface-container py-2 pr-4 pl-10 text-sm transition-all focus:ring-2 focus:ring-primary"
              placeholder="Buscar cliente..."
              type="text"
            />
          </div>
          <button
            type="button"
            className="relative flex size-10 items-center justify-center rounded-full bg-surface-container hover:bg-surface-variant"
            aria-label="Notificaciones"
          >
            <Icon name="notifications" />
            <span className="absolute top-2 right-2 size-2 rounded-full bg-error" />
          </button>
          <Button className="rounded-lg px-4 py-2 text-sm">
            <Icon name="download" className="text-sm" />
            Exportar Reporte
          </Button>
        </div>
      </header>

      <LeadFilters active={tab} onChange={setTab} />
      <LeadsTable leads={filtered} onSelect={setSelectedId} />
      <LeadDetailDrawer
        lead={selected}
        open={Boolean(selectedId)}
        onClose={() => setSelectedId(null)}
      />
    </div>
  )
}
