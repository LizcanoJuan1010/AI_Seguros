import { useEffect, useMemo, useState } from 'react'
import { Icon } from '../components/ui/Icon'
import { Button } from '../components/ui/Button'
import { LeadFilters } from '../features/agent/LeadFilters'
import { LeadsTable } from '../features/agent/LeadsTable'
import { LeadDetailDrawer } from '../features/agent/LeadDetailDrawer'
import { leads as mockLeads } from '../data/mock/leads'
import type { Lead, LeadStatus } from '../data/mock/types'
import { api, type ApiCustomer, type ApiLead } from '../lib/api'
import { useTenant } from '../tenant/TenantContext'

const TYPE_META: Record<string, { label: string; icon: string }> = {
  VIDA: { label: 'Vida', icon: 'favorite' },
  AUTO: { label: 'Auto', icon: 'directions_car' },
  SALUD: { label: 'Salud', icon: 'ecg_heart' },
}

const INTENT_META = {
  CALIENTE: { tone: 'hot', label: 'HOT' },
  TIBIO: { tone: 'warm', label: 'WARM' },
  FRIO: { tone: 'cold', label: 'COLD' },
} as const

function relativeTime(iso: string): string {
  const mins = Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 60000))
  if (mins < 60) return `Hace ${mins} min`
  if (mins < 60 * 24) return `Hace ${Math.round(mins / 60)} h`
  return `Hace ${Math.round(mins / (60 * 24))} días`
}

/** Mapea un lead del backend (+su cliente) al shape que renderiza la UI. */
function toUiLead(lead: ApiLead, customer: ApiCustomer | undefined): Lead {
  const name = customer?.fullName || 'Cliente sin nombre'
  const type = TYPE_META[lead.insuranceType ?? ''] ?? { label: 'Seguro', icon: 'shield' }
  const intent = INTENT_META[lead.intent] ?? INTENT_META.TIBIO
  const closed = lead.status.startsWith('CERRADO')
  return {
    id: lead.id,
    name,
    initials: name
      .split(' ')
      .slice(0, 2)
      .map((w) => w[0] ?? '')
      .join('')
      .toUpperCase(),
    when: relativeTime(lead.createdAt),
    type: type.label,
    typeIcon: type.icon,
    summary: `Lead ${lead.status.toLowerCase().replaceAll('_', ' ')}${customer?.city ? ` · ${customer.city}` : ''}`,
    intent: intent.tone,
    intentLabel: intent.label,
    premium: '—',
    phone: customer?.phone ?? '—',
    email: customer?.email ?? '—',
    location: customer?.city ?? 'Colombia',
    status: closed ? 'cerrados' : 'seguimiento',
    insight:
      'Lead sincronizado desde el backend multitenant. Revisa el historial con el cliente antes de llamar.',
    checks: [],
    transcript: [],
  }
}

export function AgentLeadsPage() {
  const { teamId, agents, offline } = useTenant()
  const [tab, setTab] = useState<LeadStatus>('todos')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [liveLeads, setLiveLeads] = useState<Lead[] | null>(null)

  useEffect(() => {
    if (offline) {
      setLiveLeads(null)
      return
    }
    let alive = true
    Promise.all([api.leads(), api.customers()])
      .then(([ls, cs]) => {
        if (!alive) return
        const customersById = new Map(cs.data.map((c) => [c.id, c]))
        const agentIds = new Set(agents.map((a) => a.id))
        const scoped = teamId
          ? ls.data.filter((l) => l.agentId && agentIds.has(l.agentId))
          : ls.data
        setLiveLeads(scoped.map((l) => toUiLead(l, customersById.get(l.customerId))))
      })
      .catch(() => alive && setLiveLeads(null))
    return () => {
      alive = false
    }
  }, [teamId, agents, offline])

  // Sin backend: demo con mocks. Con backend: leads reales del tenant.
  const source = liveLeads ?? mockLeads

  const filtered = useMemo(() => {
    if (tab === 'todos') return source
    return source.filter((lead) => lead.status === tab)
  }, [tab, source])

  const selected = source.find((lead) => lead.id === selectedId) ?? null

  return (
    <div className="relative flex h-full min-h-0 flex-col overflow-hidden">
      <header className="glass-header sticky top-0 z-10 flex min-h-20 flex-wrap items-center justify-between gap-3 border-b border-outline-variant px-4 py-3 md:px-8">
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
              className="w-40 rounded-lg border-none bg-surface-container py-2 pr-4 pl-10 text-sm transition-all focus:ring-2 focus:ring-primary sm:w-64"
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
