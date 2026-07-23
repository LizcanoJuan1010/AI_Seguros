/**
 * Suscripción a reportes gerenciales por correo (lógica portada de Paloma:
 * email_service SMTP→Resend + planificador de informes del servicio IA).
 * El gerente elige frecuencia; el servicio envía KPIs del negocio al correo.
 */
import { useCallback, useEffect, useState } from 'react'
import { Icon } from '../../components/ui/Icon'
import { Button } from '../../components/ui/Button'
import { useAuth } from '../../contexts/AuthContext'

type Subscription = {
  id: number
  email: string
  tipo: string
  frecuencia: string
  next_send_at?: string
}

const FRECUENCIAS = [
  { value: 'diaria', label: 'Diario' },
  { value: 'semanal', label: 'Semanal' },
  { value: 'mensual', label: 'Mensual' },
]

export function ReportsCard() {
  const { user } = useAuth()
  const [email, setEmail] = useState(user?.email ?? '')
  const [frecuencia, setFrecuencia] = useState('semanal')
  const [subs, setSubs] = useState<Subscription[]>([])
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<string | null>(null)

  const load = useCallback(() => {
    fetch('/api/reports/subscriptions')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((data: Subscription[]) => setSubs(data))
      .catch(() => setSubs([]))
  }, [])

  useEffect(load, [load])

  const subscribe = async () => {
    if (!email.trim() || busy) return
    setBusy(true)
    setNote(null)
    try {
      const res = await fetch('/api/reports/subscriptions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim(), tipo: 'gerente', frecuencia }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setNote('Suscripción guardada.')
      load()
    } catch {
      setNote('No se pudo guardar la suscripción.')
    } finally {
      setBusy(false)
    }
  }

  const remove = async (id: number) => {
    await fetch(`/api/reports/subscriptions/${id}`, { method: 'DELETE' }).catch(
      () => undefined,
    )
    load()
  }

  const sendNow = async (id: number) => {
    setNote(null)
    try {
      const res = await fetch(`/api/reports/subscriptions/${id}/send-now`, {
        method: 'POST',
      })
      const data = (await res.json()) as { status?: string; reason?: string }
      setNote(
        data.status === 'sent'
          ? 'Reporte enviado al correo.'
          : `Reporte generado (${data.status ?? 'error'}${
              data.reason ? `: ${data.reason}` : ''
            }).`,
      )
    } catch {
      setNote('No se pudo enviar el reporte.')
    }
  }

  return (
    <div className="overflow-hidden rounded-lg border border-outline-variant bg-surface-container-lowest shadow-sm">
      <div className="flex items-center gap-2 border-b border-outline-variant bg-surface-container-high px-4 py-3">
        <Icon name="outgoing_mail" className="text-primary" />
        <h3 className="text-sm font-bold text-on-surface">Reportes por correo</h3>
      </div>
      <div className="flex flex-col gap-3 p-4">
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="correo@empresa.com"
          className="w-full rounded-lg border border-outline-variant bg-white px-3 py-2 text-sm outline-none focus:border-primary"
        />
        <div className="flex gap-2">
          <select
            value={frecuencia}
            onChange={(e) => setFrecuencia(e.target.value)}
            className="flex-1 rounded-lg border border-outline-variant bg-white px-3 py-2 text-sm outline-none focus:border-primary"
          >
            {FRECUENCIAS.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </select>
          <Button
            className="rounded-lg px-4 py-2 text-sm"
            onClick={subscribe}
            disabled={busy || !email.trim()}
          >
            Suscribir
          </Button>
        </div>

        {note && <p className="text-label-sm text-on-surface-variant">{note}</p>}

        {subs.length > 0 && (
          <ul className="flex flex-col gap-2 border-t border-outline-variant/50 pt-3">
            {subs.map((s) => (
              <li
                key={s.id}
                className="flex items-center justify-between gap-2 text-sm"
              >
                <span className="min-w-0 truncate">
                  {s.email}
                  <span className="ml-1.5 rounded-full bg-primary/10 px-2 py-0.5 text-[10px] uppercase text-primary">
                    {s.tipo} · {s.frecuencia}
                  </span>
                </span>
                <span className="flex shrink-0 items-center gap-1">
                  <button
                    type="button"
                    onClick={() => sendNow(s.id)}
                    title="Enviar ahora"
                    aria-label={`Enviar reporte a ${s.email} ahora`}
                    className="flex size-8 items-center justify-center rounded-full text-on-surface-variant hover:bg-surface-variant hover:text-primary"
                  >
                    <Icon name="send" className="text-[18px]" />
                  </button>
                  <button
                    type="button"
                    onClick={() => remove(s.id)}
                    title="Cancelar suscripción"
                    aria-label={`Cancelar suscripción de ${s.email}`}
                    className="flex size-8 items-center justify-center rounded-full text-on-surface-variant hover:bg-error-container/60 hover:text-error"
                  >
                    <Icon name="delete" className="text-[18px]" />
                  </button>
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
