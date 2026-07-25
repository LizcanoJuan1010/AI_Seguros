/**
 * Adquisición por red social / canal de origen (KPI del gerente): cuántos
 * clientes llegaron por cada red y cuáles traen más. Se alimenta de
 * GET /dashboard/acquisition-by-source (agrupa customers.referral_source).
 */
import { useEffect, useState } from 'react'
import { Card } from '../../components/ui/Card'
import { Icon } from '../../components/ui/Icon'
import { api, type AcquisitionSource } from '../../lib/api'
import { useTenant } from '../../tenant/TenantContext'

/** Ícono e color por red conocida (Material Symbols no trae marcas). */
const SOURCE_META: Record<string, { icon: string; tone: string }> = {
  Instagram: { icon: 'photo_camera', tone: 'text-[#c13584]' },
  Facebook: { icon: 'thumb_up', tone: 'text-[#1877f2]' },
  TikTok: { icon: 'music_note', tone: 'text-on-surface' },
  WhatsApp: { icon: 'chat', tone: 'text-[#25d366]' },
  Google: { icon: 'search', tone: 'text-[#ea4335]' },
  YouTube: { icon: 'smart_display', tone: 'text-[#ff0000]' },
  LinkedIn: { icon: 'work', tone: 'text-[#0a66c2]' },
  Referido: { icon: 'group', tone: 'text-primary' },
  Otro: { icon: 'more_horiz', tone: 'text-on-surface-variant' },
}

function pct(n: number): string {
  return `${Math.round(n * 100)}%`
}

export function AcquisitionCard() {
  const { teamId } = useTenant()
  const [rows, setRows] = useState<AcquisitionSource[]>([])
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    let alive = true
    api
      .acquisitionBySource()
      .then((r) => alive && setRows(r.data))
      .catch(() => alive && setRows([]))
      .finally(() => alive && setLoaded(true))
    return () => {
      alive = false
    }
  }, [teamId])

  // Solo redes reales (excluye "Sin registrar" del ranking) con al menos 1.
  const named = rows.filter((r) => r.source !== 'Sin registrar' && r.count > 0)
  const unset = rows.find((r) => r.source === 'Sin registrar')?.count ?? 0

  if (!loaded) return null

  const max = Math.max(1, ...named.map((r) => r.count))
  const top = named[0]

  return (
    <Card className="rounded-lg border border-outline-variant p-5">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h2 className="text-label-md font-bold tracking-wide text-on-surface-variant uppercase">
            Adquisición por red social
          </h2>
          <p className="text-xs text-outline">
            Por dónde llegan los clientes a la plataforma
          </p>
        </div>
        <Icon
          name="share"
          className="rounded-lg bg-primary/10 p-1.5 text-primary"
        />
      </div>

      {named.length === 0 ? (
        <p className="py-6 text-center text-sm text-on-surface-variant">
          Aún no hay clientes con red social de origen registrada.
        </p>
      ) : (
        <>
          {top && (
            <div className="mb-4 flex items-center gap-2 rounded-lg bg-primary/5 px-3 py-2">
              <Icon
                name={SOURCE_META[top.source]?.icon ?? 'trending_up'}
                filled
                className={`text-[20px] ${SOURCE_META[top.source]?.tone ?? 'text-primary'}`}
              />
              <span className="text-sm text-on-surface">
                <span className="font-bold text-primary">{top.source}</span> es
                la red con mayor adquisición
                <span className="text-on-surface-variant">
                  {' '}
                  ({top.count} · {pct(top.pct)})
                </span>
              </span>
            </div>
          )}
          <ul className="flex flex-col gap-3">
            {named.map((r) => {
              const meta = SOURCE_META[r.source] ?? {
                icon: 'public',
                tone: 'text-on-surface-variant',
              }
              return (
                <li key={r.source}>
                  <div className="mb-1 flex items-center justify-between text-xs">
                    <span className="flex items-center gap-1.5 font-semibold text-on-surface">
                      <Icon name={meta.icon} filled className={`text-[16px] ${meta.tone}`} />
                      {r.source}
                    </span>
                    <span className="text-on-surface-variant">
                      <span className="font-bold text-on-surface">{r.count}</span>{' '}
                      cliente{r.count === 1 ? '' : 's'} · {pct(r.pct)}
                    </span>
                  </div>
                  <div className="h-2 w-full overflow-hidden rounded-full bg-surface-variant">
                    <div
                      className="h-full rounded-full bg-primary/70"
                      style={{ width: `${(r.count / max) * 100}%` }}
                    />
                  </div>
                </li>
              )
            })}
          </ul>
          {unset > 0 && (
            <p className="mt-3 border-t border-outline-variant/40 pt-2 text-[11px] text-outline">
              {unset} cliente{unset === 1 ? '' : 's'} sin red de origen registrada
            </p>
          )}
        </>
      )}
    </Card>
  )
}
