import { useState } from 'react'
import { Button } from '../../components/ui/Button'
import { Chip } from '../../components/ui/Chip'
import { Icon } from '../../components/ui/Icon'
import { api, type ApiCampaign } from '../../lib/api'

const INTENT_OPTIONS = [
  { value: 'CALIENTE' as const, label: 'Caliente', tone: 'hot' as const },
  { value: 'TIBIO' as const, label: 'Tibio', tone: 'warm' as const },
  { value: 'FRIO' as const, label: 'Frío', tone: 'cold' as const },
]

export function CampaignSendPanel({ campaign }: { campaign: ApiCampaign }) {
  const [intent, setIntent] = useState<'CALIENTE' | 'TIBIO' | 'FRIO'>('CALIENTE')
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<{ queued: number } | null>(null)

  async function handleSend() {
    if (!message.trim()) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const res = await api.sendCampaign(campaign.id, { intent, message })
      setResult({ queued: res.queued })
      setMessage('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo encolar el envío')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col gap-4 rounded-lg bg-surface-container-lowest p-5 soft-forest-shadow">
      <div>
        <h3 className="text-title-md font-bold text-on-surface">Enviar por WhatsApp</h3>
        <p className="text-sm text-on-surface-variant">
          Campaña: <span className="font-semibold">{campaign.phrase}</span>
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        {INTENT_OPTIONS.map((o) => (
          <button key={o.value} type="button" onClick={() => setIntent(o.value)}>
            <Chip
              tone={o.tone}
              className={intent === o.value ? 'ring-2 ring-primary' : 'opacity-60'}
            >
              {o.label}
            </Chip>
          </button>
        ))}
      </div>

      <label className="flex flex-col gap-1 text-sm font-medium text-on-surface-variant">
        Mensaje
        <textarea
          className="min-h-24 rounded-lg border border-outline-variant bg-surface px-3 py-2 text-on-surface focus:outline-none focus:ring-2 focus:ring-primary"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Hola {nombre}, tenemos una oferta especial para ti…"
        />
      </label>
      <p className="text-label-sm text-outline">
        El link del banner se agrega automáticamente al final del mensaje.
      </p>

      {result && (
        <p className="text-sm text-primary">
          {result.queued === 0
            ? 'No hay leads con consentimiento en ese segmento ahora mismo.'
            : `${result.queued} envío(s) encolado(s).`}
        </p>
      )}
      {error && <p className="text-sm text-error">{error}</p>}

      <Button variant="cta" disabled={loading || !message.trim()} onClick={handleSend}>
        <Icon name="send" className="text-[18px]" />
        {loading ? 'Encolando…' : 'Enviar al segmento'}
      </Button>
    </div>
  )
}
