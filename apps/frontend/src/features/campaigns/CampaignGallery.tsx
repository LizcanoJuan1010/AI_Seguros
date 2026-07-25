import { Card } from '../../components/ui/Card'
import { Chip } from '../../components/ui/Chip'
import { Icon } from '../../components/ui/Icon'
import type { ApiCampaign, CampaignChannel } from '../../lib/api'

const CHANNEL_LABEL: Record<CampaignChannel, string> = {
  INSTAGRAM_POST: 'Instagram · Post',
  INSTAGRAM_STORY: 'Instagram · Historia',
  LINKEDIN: 'LinkedIn',
  EMAIL: 'Correo',
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('es-CO', { day: '2-digit', month: 'short', year: 'numeric' })
}

export function CampaignGallery({
  campaigns,
  selectedId,
  onSelect,
}: {
  campaigns: ApiCampaign[]
  selectedId: string | null
  onSelect: (campaign: ApiCampaign) => void
}) {
  if (!campaigns.length) {
    return (
      <Card className="flex flex-col items-center gap-2 p-8 text-center text-on-surface-variant">
        <Icon name="campaign" className="text-[32px] text-outline" />
        <p className="text-sm">Aún no hay campañas. Crea la primera con el formulario.</p>
      </Card>
    )
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {campaigns.map((c) => (
        <Card
          key={c.id}
          className={`flex cursor-pointer flex-col overflow-hidden transition-shadow hover:shadow-lg ${
            selectedId === c.id ? 'ring-2 ring-primary' : ''
          }`}
          onClick={() => onSelect(c)}
        >
          <div className="flex aspect-video items-center justify-center bg-surface-variant">
            {c.bannerUrl ? (
              <img src={c.bannerUrl} alt={c.phrase} className="h-full w-full object-cover" />
            ) : (
              <Icon name="image" className="text-[32px] text-outline" />
            )}
          </div>
          <div className="flex flex-col gap-2 p-4">
            <p className="line-clamp-2 text-body-md font-semibold text-on-surface">{c.phrase}</p>
            <div className="flex flex-wrap items-center gap-2">
              <Chip tone="amber">{CHANNEL_LABEL[c.channel]}</Chip>
              {c.insuranceType && <Chip tone="neutral">{c.insuranceType}</Chip>}
            </div>
            <span className="text-label-sm text-outline">{formatDate(c.createdAt)}</span>
          </div>
        </Card>
      ))}
    </div>
  )
}
