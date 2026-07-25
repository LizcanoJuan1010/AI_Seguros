/**
 * Cliente hacia el servicio IA (apps/ai) para el estudio de banners de
 * marketing — vive bajo `/api/*` (no `/api/v1/*`, ese es el backend NestJS),
 * mismo proxy que ya usan useAssistantChat.ts/AssistantChat.tsx: fetch directo
 * + `authHeaders()` (el JWT del login; el endpoint exige rol gerente, ver
 * apps/ai/app/marketing_studio.py `_require_manager`).
 */
import { authHeaders } from './authFetch'

export type BannerChannel = 'instagram_post' | 'instagram_story' | 'linkedin' | 'email'

export type CreateBannerInput = {
  phrase: string
  subtitle?: string
  cta?: string
  tipo_seguro?: string
  channel: BannerChannel
  regenerar_plantilla?: boolean
}

export type CreateBannerResult = {
  ok: boolean
  demo: boolean
  file_path: string | null
  download_url: string | null
  channel?: string
  aspect_ratio?: string
  mensaje?: string
}

export async function createBanner(input: CreateBannerInput): Promise<CreateBannerResult> {
  const res = await fetch('/api/marketing/banner', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(input),
  })
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: string }
    throw new Error(body.detail || `banner → HTTP ${res.status}`)
  }
  return res.json() as Promise<CreateBannerResult>
}
