import { useEffect, useState } from 'react'
import { KpiCards } from '../features/manager/KpiCards'
import { AgentsTable } from '../features/manager/AgentsTable'
import { AlertsPanel } from '../features/manager/AlertsPanel'
import { Leaderboard } from '../features/manager/Leaderboard'
import { ReportsCard } from '../features/manager/ReportsCard'
import { AiPrediction } from '../features/manager/AiPrediction'
import { agents as mockAgents, alerts as mockAlerts, kpis as mockKpis, leaders } from '../data/mock/manager'
import type { AgentRow, Alert, Kpi } from '../data/mock/types'
import { api, formatCop, type AgentPerformance, type ApiAlert, type DailyKpis } from '../lib/api'
import { useTenant } from '../tenant/TenantContext'

const SPARK_UP = '0,35 20,30 40,32 60,15 80,18 100,5'
const SPARK_DOWN = '0,8 20,12 40,15 60,22 80,26 100,32'

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

function toAgentRows(rows: AgentPerformance[]): AgentRow[] {
  return rows.map((r) => {
    const conv = Number(r.conversionPct ?? 0)
    const good = conv >= 15
    return {
      id: r.agentId,
      name: r.fullName,
      role: `${formatCop(r.revenueMensualCop)} /mes`,
      avatar: '',
      leads: r.leadsRecibidos,
      calls: r.llamadasRealizadas,
      closes: r.polizasCerradas,
      conversion: `${conv.toLocaleString('es-CO', { maximumFractionDigits: 1 })}%`,
      conversionTone: good ? 'good' : 'warn',
      spark: good ? SPARK_UP : SPARK_DOWN,
      sparkTone: good ? 'up' : 'down',
    }
  })
}

function toAlerts(rows: ApiAlert[]): Alert[] {
  return rows
    .filter((a) => !a.resolved)
    .map((a) => ({
      id: a.id,
      title: a.severity === 'alta' ? 'Atención inmediata' : 'Aviso del equipo',
      body: a.message,
      tone: a.severity === 'alta' ? 'amber' : 'error',
      ...(a.severity === 'alta' ? { cta: 'ASIGNAR AHORA' } : {}),
    }))
}

export function ManagerDashboardPage() {
  const { teamId, team, offline } = useTenant()
  const [kpis, setKpis] = useState<Kpi[]>(mockKpis)
  const [agents, setAgents] = useState<AgentRow[]>(mockAgents)
  const [alerts, setAlerts] = useState<Alert[]>(mockAlerts)
  const [live, setLive] = useState(false)

  useEffect(() => {
    if (offline) return
    let alive = true
    Promise.all([
      api.dailyKpis(),
      api.agentPerformance(teamId || undefined),
      api.alerts(teamId || undefined),
    ])
      .then(([k, perf, al]) => {
        if (!alive) return
        setKpis(toKpis(k))
        if (perf.data.length) setAgents(toAgentRows(perf.data))
        else setAgents([])
        const mapped = toAlerts(al.data)
        setAlerts(mapped.length ? mapped : [])
        setLive(true)
      })
      .catch(() => {
        // Backend caído a mitad de sesión: conserva los datos demo.
        if (alive) setLive(false)
      })
    return () => {
      alive = false
    }
  }, [teamId, offline])

  return (
    <div className="flex flex-col gap-8 p-4 md:p-6 xl:p-8">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-headline-md font-bold text-on-surface">
            Dashboard Tequendama
          </h1>
          <p className="text-sm text-on-surface-variant">
            Supervisión de agentes, alertas y predicciones IA ·{' '}
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
        <img
          src="/assets/avatars/manager.png"
          alt="Gerente"
          className="size-10 rounded-full object-cover"
        />
      </div>

      <KpiCards items={kpis} />

      <div className="flex flex-col gap-6 lg:flex-row">
        {agents.length ? (
          <AgentsTable agents={agents} />
        ) : (
          <div className="flex flex-1 items-center justify-center rounded-lg border border-outline-variant bg-surface-container-lowest p-12 text-sm text-on-surface-variant">
            Este equipo aún no tiene actividad registrada.
          </div>
        )}
        <aside className="flex w-full flex-col gap-6 lg:w-80">
          {alerts.length > 0 && <AlertsPanel items={alerts} />}
          <Leaderboard entries={leaders} />
          <ReportsCard />
        </aside>
      </div>

      <AiPrediction />
    </div>
  )
}
