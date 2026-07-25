/**
 * Cliente tipado del backend de dominio (NestJS) — proxy nginx en `/api/v1`.
 * Todas las lecturas aceptan scoping multitenant vía `teamId` donde el
 * backend lo soporta (users, alerts, dashboard/agent-performance).
 */
import { authHeaders } from './authFetch'

const BASE = '/api/v1'

export type Paginated<T> = {
  data: T[]
  meta: { page: number; limit: number; total: number; totalPages: number }
}

export type Team = {
  id: string
  name: string
  managerId?: string | null
}

export type TeamUser = {
  id: string
  teamId: string | null
  fullName: string
  role: 'AGENTE' | 'GERENTE' | 'ADMIN'
  status: string
  avatarUrl: string | null
}

export type ApiLead = {
  id: string
  customerId: string
  agentId: string | null
  insuranceType: 'VIDA' | 'AUTO' | 'SALUD' | null
  status:
    | 'NUEVO'
    | 'CONTACTADO'
    | 'COTIZADO'
    | 'NEGOCIACION'
    | 'CERRADO_GANADO'
    | 'CERRADO_PERDIDO'
  intent: 'CALIENTE' | 'TIBIO' | 'FRIO'
  createdAt: string
}

export type ApiCustomer = {
  id: string
  fullName: string | null
  phone: string | null
  email: string | null
  city: string | null
}

export type ApiAlert = {
  id: string
  teamId: string | null
  message: string
  severity: string
  resolved: boolean
  createdAt: string
}

export type AgentPerformance = {
  agentId: string
  fullName: string
  teamId: string | null
  leadsRecibidos: number
  llamadasRealizadas: number
  polizasCerradas: number
  conversionPct: string | null
  revenueMensualCop: string | null
}

export type DailyKpis = {
  llamadasIaHoy: number
  duracionPromedioSec: number | null
  polizasHoy: number
  revenueHoyCop: string
}

export type AiImpact = {
  avgQuoteMinutes: number | null
  avgCloseDays: number | null
  conversionPct: number | null
  policiesTotal: number
  autoEmissionPct: number | null
  claimsCycleDays: number | null
  claimsOpen: number
}

export type CampaignChannel = 'INSTAGRAM_POST' | 'INSTAGRAM_STORY' | 'LINKEDIN' | 'EMAIL'

export type ApiCampaign = {
  id: string
  phrase: string
  subtitle: string | null
  cta: string | null
  insuranceType: 'VIDA' | 'AUTO' | 'SALUD' | null
  channel: CampaignChannel
  bannerUrl: string | null
  createdAt: string
  updatedAt: string
}

export type CreateCampaignInput = {
  phrase: string
  subtitle?: string
  cta?: string
  insuranceType?: 'VIDA' | 'AUTO' | 'SALUD'
  channel: CampaignChannel
  bannerUrl?: string
}

export type CampaignSendCount = {
  status: 'PENDIENTE' | 'ENVIADO' | 'FALLIDO' | 'OMITIDO'
  count: number
}

export type SendCampaignInput = { intent: 'CALIENTE' | 'TIBIO' | 'FRIO'; message: string }
export type SendCampaignResult = { queued: number; campaignId: string }

// GET /dashboard/leads-kpis (ya existía en el backend desde el motor de
// scoring; no se consumía en ningún lado del frontend todavía).
export type LeadsKpis = {
  avgFirstResponseHours: number | null
  avgCustomerResponseMinutes: number | null
  unresponsiveOver48h: { total: number; stale: number; pct: number }
  intentDistribution: { intent: 'CALIENTE' | 'TIBIO' | 'FRIO'; count: number }[]
}

export type ApiClaim = {
  id: string
  claimNumber: string
  insuranceType: 'VIDA' | 'AUTO' | 'SALUD' | null
  status: string
  description: string | null
  incidentDate: string | null
  amountEstimateCop: string | null
  fraudScore: string | null
  fraudFlags: string[] | null
  createdAt: string
}

/** Headers comunes: tenant (si hay uno seleccionado) + JWT si hay sesión
 * (OptionalJwtAuthGuard lo usa cuando está, cae al header si no — ver
 * apps/backend/src/common/jwt-auth.guard.ts). Endpoints estrictos como
 * /campaigns exigen el JWT: sin sesión, esas llamadas devuelven 401/403. */
function commonHeaders(): Record<string, string> {
  const headers: Record<string, string> = { Accept: 'application/json', ...authHeaders() }
  const tenant = getStoredTenantId()
  if (tenant) headers['X-Tenant-Id'] = tenant
  return headers
}

async function get<T>(
  path: string,
  params?: Record<string, string | undefined>,
): Promise<T> {
  const qs = new URLSearchParams()
  for (const [k, v] of Object.entries(params ?? {})) {
    if (v) qs.set(k, v)
  }
  const suffix = qs.size ? `?${qs}` : ''
  const res = await fetch(`${BASE}${path}${suffix}`, { headers: commonHeaders() })
  if (!res.ok) throw new Error(`API ${path} → HTTP ${res.status}`)
  return res.json() as Promise<T>
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { ...commonHeaders(), 'Content-Type': 'application/json' },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw new Error(`API ${path} → HTTP ${res.status}`)
  return res.json() as Promise<T>
}

export const api = {
  teams: () => get<Paginated<Team>>('/teams', { limit: '50' }),
  users: (teamId?: string) =>
    get<Paginated<TeamUser>>('/users', { teamId, limit: '100' }),
  leads: () => get<Paginated<ApiLead>>('/leads', { limit: '100' }),
  customers: () => get<Paginated<ApiCustomer>>('/customers', { limit: '100' }),
  alerts: (teamId?: string) =>
    get<Paginated<ApiAlert>>('/alerts', { teamId, limit: '20' }),
  agentPerformance: (teamId?: string) =>
    get<Paginated<AgentPerformance>>('/dashboard/agent-performance', {
      teamId,
      limit: '50',
    }),
  dailyKpis: () => get<DailyKpis>('/dashboard/daily-kpis'),
  aiImpact: () => get<AiImpact>('/dashboard/ai-impact'),
  claims: (teamId?: string) =>
    get<Paginated<ApiClaim>>('/claims', { teamId, limit: '20' }),
  campaigns: () => get<Paginated<ApiCampaign>>('/campaigns', { limit: '50' }),
  campaign: (id: string) => get<ApiCampaign>(`/campaigns/${id}`),
  campaignSendsSummary: (id: string) =>
    get<CampaignSendCount[]>(`/campaigns/${id}/sends-summary`),
  createCampaign: (input: CreateCampaignInput) =>
    post<ApiCampaign>('/campaigns', input),
  sendCampaign: (id: string, input: SendCampaignInput) =>
    post<SendCampaignResult>(`/campaigns/${id}/send`, input),
  leadsKpis: () => get<LeadsKpis>('/dashboard/leads-kpis'),
}

/** Tenant seleccionado, compartido con módulos fuera de React (ej. chat SSE). */
export const TENANT_STORAGE_KEY = 'teq_tenant_id'

export function getStoredTenantId(): string {
  try {
    return localStorage.getItem(TENANT_STORAGE_KEY) ?? ''
  } catch {
    return ''
  }
}

export function storeTenantId(id: string): void {
  try {
    if (id) localStorage.setItem(TENANT_STORAGE_KEY, id)
    else localStorage.removeItem(TENANT_STORAGE_KEY)
  } catch {
    /* almacenamiento no disponible: el tenant vive solo en memoria */
  }
}

/** Formato COP corto para KPIs ($72,4M / $504.518). */
export function formatCop(value: string | number | null | undefined): string {
  const n = Number(value ?? 0)
  if (!Number.isFinite(n) || n === 0) return '$0'
  if (Math.abs(n) >= 1_000_000) {
    return `$${(n / 1_000_000).toLocaleString('es-CO', { maximumFractionDigits: 1 })}M`
  }
  return `$${Math.round(n).toLocaleString('es-CO')}`
}
