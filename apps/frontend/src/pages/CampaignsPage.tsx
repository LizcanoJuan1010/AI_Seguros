import { useEffect, useState } from 'react'
import { CampaignForm } from '../features/campaigns/CampaignForm'
import { CampaignGallery } from '../features/campaigns/CampaignGallery'
import { CampaignMetrics } from '../features/campaigns/CampaignMetrics'
import { CampaignSendPanel } from '../features/campaigns/CampaignSendPanel'
import { api, type ApiCampaign } from '../lib/api'

export function CampaignsPage() {
  const [campaigns, setCampaigns] = useState<ApiCampaign[]>([])
  const [selected, setSelected] = useState<ApiCampaign | null>(null)
  const [loadError, setLoadError] = useState(false)

  useEffect(() => {
    let alive = true
    api
      .campaigns()
      .then((res) => alive && setCampaigns(res.data))
      .catch(() => alive && setLoadError(true))
    return () => {
      alive = false
    }
  }, [])

  function handleCreated(campaign: ApiCampaign) {
    setCampaigns((prev) => [campaign, ...prev])
    setSelected(campaign)
  }

  return (
    <div className="relative flex h-full min-h-0 flex-col overflow-y-auto">
      <header className="glass-header sticky top-0 z-10 flex min-h-20 flex-wrap items-center justify-between gap-3 border-b border-outline-variant px-4 py-3 md:px-8">
        <div>
          <h2 className="text-headline-md font-bold text-on-surface">Campañas de marketing</h2>
          <p className="text-sm font-medium text-outline">
            Banners con Gemini (paleta Colsubsidio) + envío segmentado por temperatura de lead
          </p>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-6 p-4 md:p-8 xl:grid-cols-[380px_1fr]">
        <div className="flex flex-col gap-6">
          <CampaignForm onCreated={handleCreated} />
          <CampaignMetrics />
        </div>

        <div className="flex flex-col gap-6">
          {loadError && (
            <p className="text-sm text-error">
              No se pudieron cargar las campañas existentes ahora mismo.
            </p>
          )}
          <CampaignGallery campaigns={campaigns} selectedId={selected?.id ?? null} onSelect={setSelected} />
          {selected && <CampaignSendPanel campaign={selected} />}
        </div>
      </div>
    </div>
  )
}
