import { useState } from 'react'
import { Button } from '../../components/ui/Button'
import { Icon } from '../../components/ui/Icon'
import { api, type ApiCampaign, type CampaignChannel } from '../../lib/api'
import { createBanner, type BannerChannel } from '../../lib/marketingApi'

const CHANNEL_OPTIONS: { value: BannerChannel; apiValue: CampaignChannel; label: string }[] = [
  { value: 'instagram_post', apiValue: 'INSTAGRAM_POST', label: 'Instagram (post)' },
  { value: 'instagram_story', apiValue: 'INSTAGRAM_STORY', label: 'Instagram (historia)' },
  { value: 'linkedin', apiValue: 'LINKEDIN', label: 'LinkedIn' },
  { value: 'email', apiValue: 'EMAIL', label: 'Correo' },
]

const INSURANCE_OPTIONS: { value: 'VIDA' | 'AUTO' | 'SALUD'; label: string }[] = [
  { value: 'VIDA', label: 'Vida' },
  { value: 'AUTO', label: 'Auto' },
  { value: 'SALUD', label: 'Salud' },
]

export function CampaignForm({ onCreated }: { onCreated: (campaign: ApiCampaign) => void }) {
  const [phrase, setPhrase] = useState('')
  const [subtitle, setSubtitle] = useState('')
  const [cta, setCta] = useState('')
  const [insuranceType, setInsuranceType] = useState<'VIDA' | 'AUTO' | 'SALUD' | ''>('')
  const [channel, setChannel] = useState<BannerChannel>('instagram_post')
  const [regenerarPlantilla, setRegenerarPlantilla] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!phrase.trim()) return
    setLoading(true)
    setError(null)
    setNotice(null)
    try {
      const banner = await createBanner({
        phrase,
        subtitle: subtitle || undefined,
        cta: cta || undefined,
        tipo_seguro: insuranceType ? insuranceType.toLowerCase() : undefined,
        channel,
        regenerar_plantilla: regenerarPlantilla,
      })
      if (banner.demo) setNotice(banner.mensaje ?? 'Banner simulado (falta GEMINI_API_KEY).')
      setPreviewUrl(banner.download_url)

      const channelMeta = CHANNEL_OPTIONS.find((c) => c.value === channel)!
      const campaign = await api.createCampaign({
        phrase,
        subtitle: subtitle || undefined,
        cta: cta || undefined,
        insuranceType: insuranceType || undefined,
        channel: channelMeta.apiValue,
        bannerUrl: banner.download_url ?? undefined,
      })
      onCreated(campaign)
      setPhrase('')
      setSubtitle('')
      setCta('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo crear la campaña')
    } finally {
      setLoading(false)
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex flex-col gap-4 rounded-lg bg-surface-container-lowest p-5 soft-forest-shadow"
    >
      <h3 className="text-title-md font-bold text-on-surface">Nueva campaña</h3>

      <label className="flex flex-col gap-1 text-sm font-medium text-on-surface-variant">
        Titular
        <input
          className="rounded-lg border border-outline-variant bg-surface px-3 py-2 text-on-surface focus:outline-none focus:ring-2 focus:ring-primary"
          value={phrase}
          onChange={(e) => setPhrase(e.target.value)}
          placeholder="Ej. Protege a tu familia desde hoy"
          required
        />
      </label>

      <label className="flex flex-col gap-1 text-sm font-medium text-on-surface-variant">
        Subtítulo (opcional)
        <input
          className="rounded-lg border border-outline-variant bg-surface px-3 py-2 text-on-surface focus:outline-none focus:ring-2 focus:ring-primary"
          value={subtitle}
          onChange={(e) => setSubtitle(e.target.value)}
        />
      </label>

      <label className="flex flex-col gap-1 text-sm font-medium text-on-surface-variant">
        Llamado a la acción (opcional)
        <input
          className="rounded-lg border border-outline-variant bg-surface px-3 py-2 text-on-surface focus:outline-none focus:ring-2 focus:ring-primary"
          value={cta}
          onChange={(e) => setCta(e.target.value)}
          placeholder="Cotiza ahora"
        />
      </label>

      <div className="grid grid-cols-2 gap-3">
        <label className="flex flex-col gap-1 text-sm font-medium text-on-surface-variant">
          Tipo de seguro
          <select
            className="rounded-lg border border-outline-variant bg-surface px-3 py-2 text-on-surface"
            value={insuranceType}
            onChange={(e) => setInsuranceType(e.target.value as typeof insuranceType)}
          >
            <option value="">Sin especificar</option>
            {INSURANCE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1 text-sm font-medium text-on-surface-variant">
          Canal
          <select
            className="rounded-lg border border-outline-variant bg-surface px-3 py-2 text-on-surface"
            value={channel}
            onChange={(e) => setChannel(e.target.value as BannerChannel)}
          >
            {CHANNEL_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <label className="flex items-center gap-2 text-sm font-medium text-on-surface-variant">
        <input
          type="checkbox"
          checked={regenerarPlantilla}
          onChange={(e) => setRegenerarPlantilla(e.target.checked)}
        />
        Forzar diseño base nuevo para este canal
      </label>

      {previewUrl && (
        <img
          src={previewUrl}
          alt="Vista previa del banner"
          className="max-h-64 w-full rounded-lg border border-outline-variant object-contain"
        />
      )}

      {notice && <p className="text-sm text-secondary">{notice}</p>}
      {error && <p className="text-sm text-error">{error}</p>}

      <Button type="submit" variant="cta" disabled={loading || !phrase.trim()}>
        <Icon name="auto_awesome" className="text-[18px]" />
        {loading ? 'Generando…' : 'Generar banner y crear campaña'}
      </Button>
    </form>
  )
}
