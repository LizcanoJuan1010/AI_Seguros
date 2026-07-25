/**
 * Leads calientes sin contactar (pestaña Funnel): la lista accionable que ya
 * calculaba el backend (GET /dashboard/hot-leads-uncontacted) — leads con
 * intención caliente, nuevos y sin primer contacto pasado el umbral de horas.
 */
import { useEffect, useState } from 'react'
import { Card } from '../../components/ui/Card'
import { Icon } from '../../components/ui/Icon'
import { api, type HotLead } from '../../lib/api'
import { useTenant } from '../../tenant/TenantContext'

export function HotLeadsCard() {
  const { teamId } = useTenant()
  const [leads, setLeads] = useState<HotLead[]>([])
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    let alive = true
    api
      .hotLeadsUncontacted()
      .then((d) => {
        if (!alive) return
        setLeads(d.data)
        setLoaded(true)
      })
      .catch(() => {
        if (!alive) return
        setLeads([])
        setLoaded(true)
      })
    return () => {
      alive = false
    }
  }, [teamId])

  if (!loaded) return null

  return (
    <Card className="rounded-lg border-2 border-amber-cta">
      <div className="flex items-center gap-2 border-b border-outline-variant bg-amber-cta/10 p-5">
        <Icon name="local_fire_department" className="text-amber-cta" />
        <div>
          <h2 className="text-lg font-bold text-on-surface">
            Leads calientes sin contactar
          </h2>
          <p className="text-xs text-on-surface-variant">
            Alta intención y aún sin primer toque — acción prioritaria de hoy
          </p>
        </div>
        <span className="ml-auto rounded-full bg-amber-cta px-2.5 py-1 text-xs font-bold text-primary">
          {leads.length}
        </span>
      </div>
      {leads.length === 0 ? (
        <p className="flex items-center gap-2 p-6 text-sm text-on-surface-variant">
          <Icon name="check_circle" className="text-primary" />
          Ningún lead caliente quedó sin contactar. Buen trabajo del equipo.
        </p>
      ) : (
        <ul className="divide-y divide-outline-variant">
          {leads.map((l) => (
            <li key={l.id} className="flex items-center justify-between gap-3 p-4">
              <div className="min-w-0">
                <p className="text-sm font-semibold text-on-surface">
                  {l.agentName ?? 'Sin asignar'}
                </p>
                <p className="font-mono text-[11px] text-outline">
                  Lead {l.id.slice(0, 8)}
                </p>
              </div>
              <span
                className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-bold ${
                  l.horasSinContacto >= 24
                    ? 'bg-error-container text-on-error-container'
                    : 'bg-amber-cta/20 text-on-secondary-fixed-variant'
                }`}
              >
                {l.horasSinContacto} h sin contacto
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}
