/**
 * Ranking de combos de seguros (pestaña Resumen del gerente): combinaciones
 * de tipos de seguro que un mismo cliente tiene VIGENTES a la vez — cross-sell
 * real, no cotizaciones (GET /api/insights/combos del servicio IA, mismo
 * patrón de fetch que ProductIdeasWall.tsx). Requiere sesión de gerente; si
 * no hay permiso o no hay combos todavía, no se muestra nada.
 */
import { useEffect, useState } from 'react'
import { Card } from '../../components/ui/Card'
import { Icon } from '../../components/ui/Icon'
import { authHeaders } from '../../lib/authFetch'
import { useTenant } from '../../tenant/TenantContext'

type Combo = {
  combo: string[]
  clientes: number
}

type CombosResponse = {
  combos: Combo[]
}

const TIPO_LABEL: Record<string, string> = {
  VIDA: 'Vida',
  AUTO: 'Auto',
  SALUD: 'Salud',
  HOGAR: 'Hogar',
  VIAJE: 'Viaje',
  PYME: 'Pyme',
  ACCIDENTES: 'Accidentes',
  EXEQUIAL: 'Exequial',
  MASCOTAS: 'Mascotas',
  MOVILIDAD: 'Movilidad',
}

function tipoLabel(tipo: string): string {
  return TIPO_LABEL[tipo] ?? tipo
}

export function ComboRankingCard() {
  const { teamId } = useTenant()
  const [data, setData] = useState<CombosResponse | null>(null)

  useEffect(() => {
    let alive = true
    fetch('/api/insights/combos', { headers: authHeaders() })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d: CombosResponse) => alive && setData(d))
      .catch(() => alive && setData(null))
    return () => {
      alive = false
    }
  }, [teamId])

  if (!data || data.combos.length === 0) return null

  const max = Math.max(...data.combos.map((c) => c.clientes))

  return (
    <Card className="rounded-lg border border-outline-variant p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-bold text-on-surface">
            <Icon name="stacked_line_chart" className="text-primary" />
            Combos más comprados
          </h2>
          <p className="text-xs text-on-surface-variant">
            Combinaciones de seguros vigentes que un mismo cliente tiene a la vez
          </p>
        </div>
        <span className="rounded-full bg-primary/10 px-2.5 py-1 text-[11px] font-bold text-primary">
          {data.combos.length} combo(s)
        </span>
      </div>

      <div className="flex flex-col gap-3">
        {data.combos.map((c) => {
          const pct = Math.round((c.clientes / max) * 100)
          return (
            <div key={c.combo.join('+')} className="flex flex-col gap-1">
              <div className="flex items-center justify-between gap-2">
                <span className="flex flex-wrap items-center gap-1.5 text-sm font-semibold text-on-surface">
                  {c.combo.map((tipo, i) => (
                    <span key={tipo} className="flex items-center gap-1.5">
                      {i > 0 && <Icon name="add" className="text-[13px] text-outline" />}
                      <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-bold text-primary">
                        {tipoLabel(tipo)}
                      </span>
                    </span>
                  ))}
                </span>
                <span className="shrink-0 text-xs font-bold text-on-surface-variant">
                  {c.clientes} cliente(s)
                </span>
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-variant">
                <div className="h-full bg-primary/60" style={{ width: `${pct}%` }} />
              </div>
            </div>
          )
        })}
      </div>
    </Card>
  )
}
