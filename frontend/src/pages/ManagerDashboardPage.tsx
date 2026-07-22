import { KpiCards } from '../features/manager/KpiCards'
import { AgentsTable } from '../features/manager/AgentsTable'
import { AlertsPanel } from '../features/manager/AlertsPanel'
import { Leaderboard } from '../features/manager/Leaderboard'
import { AiPrediction } from '../features/manager/AiPrediction'
import { agents, alerts, kpis, leaders } from '../data/mock/manager'

export function ManagerDashboardPage() {
  return (
    <div className="flex flex-col gap-8 overflow-y-auto p-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-headline-md font-bold text-on-surface">
            Dashboard Tequendama
          </h1>
          <p className="text-sm text-on-surface-variant">
            Supervisión de agentes, alertas y predicciones IA
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
        <AgentsTable agents={agents} />
        <aside className="flex w-full flex-col gap-6 lg:w-80">
          <AlertsPanel items={alerts} />
          <Leaderboard entries={leaders} />
        </aside>
      </div>

      <AiPrediction />
    </div>
  )
}
