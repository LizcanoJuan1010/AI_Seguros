/**
 * Salud de la cola priorizada por agente (pestaña Equipo): cuántos leads
 * abiertos lleva cada asesor y su reparto urgente/normal/bajo, según el
 * priorityScore del motor de leads (GET /dashboard/queue-health). Cruza el
 * agentId con los nombres del tenant.
 */
import { useEffect, useMemo, useState } from 'react'
import { Card } from '../../components/ui/Card'
import { Icon } from '../../components/ui/Icon'
import { api, type QueueHealth } from '../../lib/api'
import { useTenant } from '../../tenant/TenantContext'

export function QueueHealthCard() {
  const { teamId, agents } = useTenant()
  const [rows, setRows] = useState<QueueHealth[]>([])

  useEffect(() => {
    let alive = true
    api
      .queueHealth()
      .then((d) => alive && setRows(d))
      .catch(() => alive && setRows([]))
    return () => {
      alive = false
    }
  }, [teamId])

  const nameById = useMemo(
    () => new Map(agents.map((a) => [a.id, a.fullName])),
    [agents],
  )

  if (rows.length === 0) return null

  const maxTotal = Math.max(1, ...rows.map((r) => r.total))

  return (
    <Card className="rounded-lg border border-outline-variant">
      <div className="border-b border-outline-variant p-5">
        <h2 className="flex items-center gap-2 text-lg font-bold text-on-surface">
          <Icon name="format_list_numbered" className="text-primary" />
          Carga de la cola por asesor
        </h2>
        <p className="text-xs text-on-surface-variant">
          Leads abiertos y su urgencia según el score de prioridad de la IA
        </p>
      </div>
      <div className="flex flex-col divide-y divide-outline-variant">
        {rows.map((r) => {
          const name = r.agentId
            ? (nameById.get(r.agentId) ?? 'Asesor')
            : 'Sin asignar'
          return (
            <div key={r.agentId ?? 'none'} className="flex items-center gap-4 p-4">
              <div className="min-w-0 flex-1">
                <div className="mb-1 flex items-center justify-between gap-2">
                  <p className="truncate text-sm font-bold text-on-surface">
                    {name}
                  </p>
                  <span className="text-xs text-on-surface-variant">
                    {r.total} lead(s) · score prom. {r.avgPriorityScore}
                  </span>
                </div>
                <div className="flex h-2.5 overflow-hidden rounded-full bg-surface-variant">
                  <div
                    className="bg-error"
                    style={{ width: `${(r.urgent / maxTotal) * 100}%` }}
                    title={`${r.urgent} urgentes`}
                  />
                  <div
                    className="bg-amber-cta"
                    style={{ width: `${(r.normal / maxTotal) * 100}%` }}
                    title={`${r.normal} en seguimiento`}
                  />
                  <div
                    className="bg-primary/50"
                    style={{ width: `${(r.low / maxTotal) * 100}%` }}
                    title={`${r.low} de baja prioridad`}
                  />
                </div>
                <div className="mt-1 flex gap-3 text-[10px] text-on-surface-variant">
                  <span className="flex items-center gap-1">
                    <span className="size-2 rounded-full bg-error" /> {r.urgent} urgente
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="size-2 rounded-full bg-amber-cta" /> {r.normal} seguimiento
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="size-2 rounded-full bg-primary/50" /> {r.low} bajo
                  </span>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </Card>
  )
}
