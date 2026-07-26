/**
 * Salud del funnel comercial: velocidad de respuesta (leads-kpis) y
 * progresión/conversión por canal de origen (channel-funnel). Ambos ya los
 * calculaba el motor de leads del backend; esta tarjeta los hace visibles
 * para el gerente.
 */
import { useEffect, useState } from 'react'
import { Card } from '../../components/ui/Card'
import { Icon } from '../../components/ui/Icon'
import { api, type ChannelFunnel, type LeadsKpis } from '../../lib/api'
import { useTenant } from '../../tenant/TenantContext'

const CHANNEL_LABEL: Record<string, string> = {
  WEB_INTEREST: 'Interés web',
  WEB_CHAT: 'Chat web',
  WHATSAPP: 'WhatsApp',
  EMAIL: 'Email',
  VOICE_CALL: 'Llamada',
}

function fmt(value: number | null | undefined, digits = 1): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return value.toLocaleString('es-CO', { maximumFractionDigits: digits })
}

function Metric({
  icon,
  label,
  value,
  hint,
}: {
  icon: string
  label: string
  value: string
  hint: string
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="flex items-center gap-1 text-xs font-medium text-on-surface-variant">
        <Icon name={icon} className="text-sm text-primary" />
        {label}
      </span>
      <span className="text-2xl font-bold text-on-surface">{value}</span>
      <span className="text-[10px] text-outline">{hint}</span>
    </div>
  )
}

export function FunnelHealthCard() {
  const { teamId } = useTenant()
  const [kpis, setKpis] = useState<LeadsKpis | null>(null)
  const [funnel, setFunnel] = useState<ChannelFunnel | null>(null)

  useEffect(() => {
    let alive = true
    api
      .leadsKpis()
      .then((d) => alive && setKpis(d))
      .catch(() => alive && setKpis(null))
    api
      .channelFunnel()
      .then((d) => alive && setFunnel(d))
      .catch(() => alive && setFunnel(null))
    return () => {
      alive = false
    }
  }, [teamId])

  if (!kpis && !funnel) return null

  const channels = (funnel?.conversionByFirstChannel ?? [])
    .slice()
    .sort((a, b) => b.total - a.total)
  const maxTotal = Math.max(1, ...channels.map((c) => c.total))

  return (
    <Card className="rounded-lg border border-outline-variant p-5">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-label-md font-bold tracking-wide text-on-surface-variant uppercase">
            Salud del funnel
          </h2>
          <p className="text-xs text-outline">
            Velocidad de respuesta y conversión por canal de origen
          </p>
        </div>
        <Icon
          name="conversion_path"
          className="rounded-lg bg-primary/10 p-1.5 text-primary"
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_1.2fr]">
        {kpis && (
          <div className="grid grid-cols-1 gap-4 xs:grid-cols-2">
            <Metric
              icon="bolt"
              label="Primera respuesta"
              value={kpis.avgFirstResponseHours != null ? `${fmt(kpis.avgFirstResponseHours)} h` : '—'}
              hint="Del lead nuevo al primer toque"
            />
            <Metric
              icon="forum"
              label="Cliente responde en"
              value={
                kpis.avgCustomerResponseMinutes != null
                  ? `${fmt(kpis.avgCustomerResponseMinutes)} min`
                  : '—'
              }
              hint="Latencia media en conversación"
            />
            <Metric
              icon="hourglass_bottom"
              label="Leads +48h sin respuesta"
              value={`${fmt(kpis.unresponsiveOver48h.pct * 100, 0)}%`}
              hint={`${kpis.unresponsiveOver48h.stale} de ${kpis.unresponsiveOver48h.total} abiertos`}
            />
            <Metric
              icon="moving"
              label="Escalan de canal"
              value={funnel ? `${fmt(funnel.channelEscalationRate * 100, 0)}%` : '—'}
              hint={
                funnel
                  ? `${fmt(funnel.reachedVoiceCallPct * 100, 0)}% llegan a llamada`
                  : 'Ej: WhatsApp → llamada'
              }
            />
          </div>
        )}

        {channels.length > 0 && (
          <div className="flex flex-col gap-3">
            <p className="text-xs font-semibold text-on-surface-variant">
              Conversión por canal de entrada
            </p>
            {channels.map((c) => {
              const label = c.channel
                ? (CHANNEL_LABEL[c.channel] ?? c.channel)
                : 'Sin canal'
              return (
                <div key={c.channel ?? 'none'}>
                  <div className="mb-1 flex items-center justify-between text-xs">
                    <span className="text-on-surface">{label}</span>
                    <span className="text-on-surface-variant">
                      {c.won}/{c.total} ganados ·{' '}
                      <span className="font-bold text-primary">
                        {fmt(c.conversionPct * 100, 0)}%
                      </span>
                    </span>
                  </div>
                  <div className="h-2 w-full overflow-hidden rounded-full bg-surface-variant">
                    <div
                      className="h-full rounded-full bg-primary/70"
                      style={{ width: `${(c.total / maxTotal) * 100}%` }}
                    />
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </Card>
  )
}
