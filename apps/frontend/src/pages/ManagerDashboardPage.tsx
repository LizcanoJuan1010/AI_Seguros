import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Icon } from '../components/ui/Icon'
import { KpiCards } from '../features/manager/KpiCards'
import { AlertsPanel } from '../features/manager/AlertsPanel'
import { ReportsCard } from '../features/manager/ReportsCard'
import { AiPrediction } from '../features/manager/AiPrediction'
import { AiImpactCard } from '../features/manager/AiImpactCard'
import { ClaimsPanel } from '../features/manager/ClaimsPanel'
import { CustomerPortfolio } from '../features/manager/CustomerPortfolio'
import { FunnelHealthCard } from '../features/manager/FunnelHealthCard'
import { ProductIdeasWall } from '../features/manager/ProductIdeasWall'
import { AgentKnowledgePanel } from '../features/manager/AgentKnowledgePanel'
import { HotLeadsCard } from '../features/manager/HotLeadsCard'
import { kpis as mockKpis } from '../data/mock/manager'
import type { Alert, Kpi } from '../data/mock/types'
import {
  api,
  formatCop,
  type AiImpact,
  type ApiClaim,
  type DailyKpis,
  type DashboardAlertItem,
} from '../lib/api'
import { useTenant } from '../tenant/TenantContext'


type TabId = 'resumen' | 'clientes' | 'funnel' | 'reclamos' | 'agente'

const TABS: { id: TabId; label: string; icon: string }[] = [
  { id: 'resumen', label: 'Resumen', icon: 'dashboard' },
  { id: 'clientes', label: 'Clientes', icon: 'diversity_3' },
  { id: 'funnel', label: 'Funnel', icon: 'conversion_path' },
  { id: 'reclamos', label: 'Reclamos', icon: 'health_and_safety' },
  { id: 'agente', label: 'Agente IA', icon: 'smart_toy' },
]

function toKpis(k: DailyKpis): Kpi[] {
  const dur = k.duracionPromedioSec
  return [
    {
      id: 'calls',
      label: 'Llamadas IA hoy',
      value: k.llamadasIaHoy.toLocaleString('es-CO'),
      delta: 'en vivo',
      deltaUp: true,
      hint: 'Registradas por el backend',
      icon: 'smart_toy',
    },
    {
      id: 'policies',
      label: 'Pólizas hoy',
      value: k.polizasHoy.toLocaleString('es-CO'),
      delta: 'en vivo',
      deltaUp: true,
      hint: 'Cierres autónomos IA',
      icon: 'verified',
    },
    {
      id: 'rev',
      label: 'Ingresos hoy (COP)',
      value: formatCop(k.revenueHoyCop),
      delta: 'en vivo',
      deltaUp: true,
      hint: 'Primas de pólizas emitidas',
      icon: 'payments',
    },
    {
      id: 'aht',
      label: 'Tiempo Prom. (AHT)',
      value: dur
        ? `${Math.floor(dur / 60)}:${String(Math.round(dur % 60)).padStart(2, '0')} min`
        : '—',
      delta: 'en vivo',
      deltaUp: true,
      hint: 'Duración media de llamada IA',
      icon: 'timer',
    },
  ]
}


export function ManagerDashboardPage() {
  const { teamId, team, offline } = useTenant()
  const [searchParams, setSearchParams] = useSearchParams()
  const tabParam = searchParams.get('tab') as TabId | null
  const activeTab: TabId = TABS.some((t) => t.id === tabParam)
    ? (tabParam as TabId)
    : 'resumen'

  const [kpis, setKpis] = useState<Kpi[]>(mockKpis)
  const [impact, setImpact] = useState<AiImpact | null>(null)
  const [claims, setClaims] = useState<ApiClaim[]>([])
  const [alerts, setAlerts] = useState<DashboardAlertItem[]>([])
  const [live, setLive] = useState(false)

  useEffect(() => {
    if (offline) return
    let alive = true
    api
      .dailyKpis()
      .then((k) => {
        if (!alive) return
        setKpis(toKpis(k))
        setLive(true)
      })
      .catch(() => {
        // Backend caído a mitad de sesión: conserva los datos demo.
        if (alive) setLive(false)
      })
    // Métricas de impacto IA y reclamos: opcionales, cada una degrada sola.
    api
      .aiImpact()
      .then((d) => alive && setImpact(d))
      .catch(() => alive && setImpact(null))
    api
      .claims(teamId || undefined)
      .then((c) => alive && setClaims(c.data))
      .catch(() => alive && setClaims([]))
    // Alertas críticas: derivadas EN VIVO del riesgo de los clientes.
    api
      .dashboardAlerts()
      .then((r) => alive && setAlerts(r.data))
      .catch(() => alive && setAlerts([]))
    return () => {
      alive = false
    }
  }, [teamId, offline])

  /** Alertas del backend → forma que renderiza AlertsPanel. */
  const alertItems: Alert[] = alerts.map((a) => ({
    id: a.id,
    title: a.title,
    body: a.message,
    tone: a.severity === 'alta' ? 'error' : 'amber',
  }))

  const setTab = (id: TabId) => {
    const next = new URLSearchParams(searchParams)
    if (id === 'resumen') next.delete('tab')
    else next.set('tab', id)
    setSearchParams(next, { replace: true })
  }

  const openClaims = claims.length

  return (
    <div className="flex flex-col gap-6 p-4 md:p-6 xl:p-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-headline-md font-bold text-on-surface">
            Dashboard Tequendama
          </h1>
          <p className="text-sm text-on-surface-variant">
            Panel del gerente ·{' '}
            <span className="font-bold text-primary">
              {team?.name ?? 'Todos los equipos'}
            </span>
            {live && (
              <span className="ml-2 inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-bold uppercase text-primary">
                <span className="size-1.5 animate-pulse rounded-full bg-primary" />
                datos en vivo
              </span>
            )}
          </p>
        </div>
      </div>

      {/* Pestañas: el alcance (equipo) es transversal y vive en el encabezado. */}
      <nav
        aria-label="Secciones del dashboard"
        className="flex gap-1 overflow-x-auto border-b border-outline-variant"
      >
        {TABS.map((t) => {
          const isActive = t.id === activeTab
          const badge =
            t.id === 'resumen' && alerts.length > 0
              ? alerts.length
              : t.id === 'reclamos' && openClaims > 0
                ? openClaims
                : null
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`flex shrink-0 items-center gap-2 border-b-2 px-4 py-3 text-sm font-semibold transition-colors ${
                isActive
                  ? 'border-primary text-primary'
                  : 'border-transparent text-on-surface-variant hover:text-on-surface'
              }`}
            >
              <Icon name={t.icon} filled={isActive} className="text-[18px]" />
              {t.label}
              {badge != null && (
                <span className="rounded-full bg-error px-1.5 py-0.5 text-[10px] font-bold text-white">
                  {badge}
                </span>
              )}
            </button>
          )
        })}
      </nav>

      {activeTab === 'resumen' && (
        <div className="flex flex-col gap-6">
          {/* Pulso del día → impacto de la IA → mirada a futuro → oportunidades */}
          <KpiCards items={kpis} />
          {impact && <AiImpactCard data={impact} />}
          <div className="flex flex-col gap-6 lg:flex-row">
            <div className="flex-1">
              <AiPrediction />
            </div>
            <aside className="flex w-full flex-col gap-6 lg:w-80">
              {alertItems.length > 0 && <AlertsPanel items={alertItems} />}
              <ReportsCard />
            </aside>
          </div>
          <ProductIdeasWall />
        </div>
      )}

      {activeTab === 'clientes' && <CustomerPortfolio />}

      {activeTab === 'funnel' && (
        <div className="flex flex-col gap-6">
          <FunnelHealthCard />
          <HotLeadsCard />
        </div>
      )}

      {activeTab === 'reclamos' && (
        <div className="flex flex-col gap-6">
          {claims.length > 0 ? (
            <ClaimsPanel items={claims} />
          ) : (
            <div className="flex items-center justify-center rounded-lg border border-outline-variant bg-surface-container-lowest p-12 text-sm text-on-surface-variant">
              No hay reclamos registrados para este equipo.
            </div>
          )}
        </div>
      )}

      {activeTab === 'agente' && <AgentKnowledgePanel />}
    </div>
  )
}
