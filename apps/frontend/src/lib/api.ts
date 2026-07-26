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
  notes?: string | null
}

/** Payload de crear/editar cliente (coincide con CreateCustomerDto del backend). */
export type CustomerInput = {
  fullName?: string
  documentType?: string
  documentId?: string
  email?: string
  phone?: string
  birthDate?: string
  city?: string
  department?: string
  consentData?: boolean
  notes?: string
  referralSource?: string
  referralLink?: string
}

/** Adquisición por red social / canal de origen. */
export type AcquisitionSource = {
  source: string
  count: number
  pct: number
}

/** Archivo adjunto a un cliente (metadata; el binario vive en el backend). */
export type CustomerAttachment = {
  id: string
  customerId: string
  filename: string
  mimeType: string
  sizeBytes: number
  kind: string | null
  createdAt: string
}

/** Alerta crítica computada en vivo desde el riesgo del cliente. */
export type DashboardAlertItem = {
  id: string
  severity: 'alta' | 'media'
  title: string
  message: string
  customerId: string
  kind: string
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

export type RiskLevel = 'alto' | 'medio' | 'bajo'

export type PortfolioLead = {
  id: string
  status: ApiLead['status']
  intent: ApiLead['intent']
  priorityScore: number
  firstChannel: string | null
  highestChannel: string | null
  insuranceType: 'VIDA' | 'AUTO' | 'SALUD' | null
  agentName: string | null
  hoursSinceResponse: number | null
  uncontacted: boolean
}

export type PortfolioCustomer = {
  customerId: string
  fullName: string | null
  phone: string | null
  email: string | null
  city: string | null
  documentId: string | null
  createdAt: string
  lead: PortfolioLead | null
  policies: { active: number; total: number; monthlyPremiumCop: number }
  claims: { open: number; total: number; maxFraudScore: number | null }
  calls: { total: number; lastAt: string | null }
  risk: { level: RiskLevel; factors: string[] }
}

export type PortfolioSummary = {
  totalCustomers: number
  openLeads: number
  hotUncontacted: number
  unresponsive48h: number
  activePolicies: number
  monthlyPremiumCop: number
  openClaims: number
  fraudSuspects: number
  byIntent: { caliente: number; tibio: number; frio: number }
  byRisk: { alto: number; medio: number; bajo: number }
}

export type CustomerPortfolio = Paginated<PortfolioCustomer> & {
  summary: PortfolioSummary
}

export type PortfolioFilters = {
  search?: string
  intent?: string
  status?: string
  insuranceType?: string
  risk?: string
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

export type ChannelFunnel = {
  conversionByFirstChannel: {
    channel: string | null
    total: number
    won: number
    conversionPct: number
  }[]
  channelEscalationRate: number
  reachedVoiceCallPct: number
}

export type QueueHealth = {
  agentId: string | null
  total: number
  avgPriorityScore: number
  urgent: number
  normal: number
  low: number
}

export type HotLead = {
  id: string
  agentId: string | null
  agentName: string | null
  createdAt: string
  horasSinContacto: number
}

export type ApiClaim = {
  id: string
  claimNumber: string
  customerId: string | null
  customerName: string | null
  insuranceType: 'VIDA' | 'AUTO' | 'SALUD' | null
  status: string
  description: string | null
  incidentDate: string | null
  amountEstimateCop: string | null
  fraudScore: string | null
  fraudFlags: string[] | null
  createdAt: string
}

/** Perfil calculado por el servicio IA (seguria.customer_profile.perfil). */
export type AiPerfil = {
  edad?: number
  dependientes?: number
  banderas?: string[]
  etapa_vida?: string
  resumen_perfil?: string
  nivel_capacidad?: string
  segmento_riesgo?: string
  propension_compra?: number
  necesidades_detectadas?: { tipo: string; razon?: string; prioridad?: string }[]
  productos_recomendados?: {
    tipo: string
    prioridad?: string
    producto_id?: string
  }[]
  segmento_riesgo_motivos?: string[]
  capacidad_pago_mensual_cop?: number
}

export type FullLeadEvent = {
  id: string
  eventType: string
  notes: string | null
  payload: unknown
  createdAt: string
  agentName: string | null
}

export type FullLead = {
  id: string
  status: ApiLead['status']
  intent: ApiLead['intent']
  insuranceType: 'VIDA' | 'AUTO' | 'SALUD' | null
  priorityScore: number
  firstChannel: string | null
  highestChannel: string | null
  agentName: string | null
  createdAt: string
  firstContactAt: string | null
  lastCustomerResponseAt: string | null
  closedAt: string | null
  lostReason: string | null
  aiNextSteps: unknown
  events: FullLeadEvent[]
}

export type FullQuote = {
  id: string
  monthlyPremiumCop: string
  status: string
  validUntil: string | null
  createdAt: string
  coverage: Record<string, unknown> | null
  product: { name: string; insuranceType: string } | null
}

export type FullPolicy = {
  id: string
  policyNumber: string
  status: string
  startDate: string
  endDate: string
  monthlyPremiumCop: string
  createdAt: string
}

export type FullCallMessage = {
  id: string
  speaker: 'IA' | 'CLIENTE'
  content: string
  spokenAt: string
}

export type FullAiCall = {
  id: string
  channel: string
  status: string
  startedAt: string
  durationSec: number | null
  summary: string | null
  intent: string | null
  sentiment: string | null
  messages: FullCallMessage[]
}

export type ConversationTurn = {
  role: string
  message: string
  channel: string | null
  createdAt: string
}

/** Cliente 360 (GET /customers/:id/full): todo lo que el sistema sabe de él. */
export type CustomerFull = {
  customer: {
    id: string
    fullName: string | null
    email: string | null
    phone: string | null
    documentType: string | null
    documentId: string | null
    birthDate: string | null
    edad: number | null
    city: string | null
    department: string | null
    consentData: boolean
    consentAt: string | null
    notes?: string | null
    referralSource?: string | null
    referralLink?: string | null
    createdAt: string
  }
  documents?: CustomerAttachment[]
  aiProfile: { perfil: AiPerfil; fuente: string | null; updatedAt: string } | null
  intake: { datos: Record<string, unknown>; updatedAt: string } | null
  conversation: ConversationTurn[]
  leads: FullLead[]
  quotes: FullQuote[]
  policies: FullPolicy[]
  claims: ApiClaim[]
  aiCalls: FullAiCall[]
}

/** Documento firmado/generado del cliente (viene en intake.datos.documentos). */
export type CustomerDocument = {
  nombre: string
  tipo?: string
  archivo?: string
  firmado?: boolean
  fecha?: string
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
  const res = await fetch(`${BASE}${path}${suffix}`, { headers: baseHeaders() })
  if (!res.ok) throw new Error(`API ${path} → HTTP ${res.status}`)
  return res.json() as Promise<T>
}

/** Headers comunes: tenant activo + Bearer si hay sesión. */
function baseHeaders(): Record<string, string> {
  const headers: Record<string, string> = {
    Accept: 'application/json',
    ...authHeaders(),
  }
  const tenant = getStoredTenantId()
  if (tenant) headers['X-Tenant-Id'] = tenant
  return headers
}

/** Extrae el mensaje de error del backend (Nest: { message }) para la UI. */
async function toError(res: Response, path: string): Promise<Error> {
  try {
    const body = (await res.json()) as { message?: string | string[] }
    const msg = Array.isArray(body.message)
      ? body.message.join(', ')
      : body.message
    if (msg) return new Error(msg)
  } catch {
    /* cuerpo no-JSON */
  }
  return new Error(`API ${path} → HTTP ${res.status}`)
}

async function send<T>(
  method: 'POST' | 'PATCH' | 'DELETE',
  path: string,
  body?: unknown,
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: { ...baseHeaders(), 'Content-Type': 'application/json' },
    ...(body !== undefined && { body: JSON.stringify(body) }),
  })
  if (!res.ok) throw await toError(res, path)
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

const post = <T>(path: string, body?: unknown) => send<T>('POST', path, body)
const patch = <T>(path: string, body?: unknown) => send<T>('PATCH', path, body)
const del = (path: string) => send<void>('DELETE', path)

/** Envío multipart (sin Content-Type: el navegador pone el boundary). */
async function postForm<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: baseHeaders(),
    body: form,
  })
  if (!res.ok) throw await toError(res, path)
  return res.json() as Promise<T>
}

export const api = {
  teams: () => get<Paginated<Team>>('/teams', { limit: '50' }),
  users: (teamId?: string) =>
    get<Paginated<TeamUser>>('/users', { teamId, limit: '100' }),
  leads: () => get<Paginated<ApiLead>>('/leads', { limit: '100' }),
  customers: () => get<Paginated<ApiCustomer>>('/customers', { limit: '100' }),
  customerFull: (id: string) => get<CustomerFull>(`/customers/${id}/full`),
  createCustomer: (input: CustomerInput) =>
    post<ApiCustomer>('/customers', input),
  updateCustomer: (id: string, input: CustomerInput) =>
    patch<ApiCustomer>(`/customers/${id}`, input),
  deleteCustomer: (id: string) => del(`/customers/${id}`),
  uploadCustomerDocuments: (id: string, files: File[]) => {
    const form = new FormData()
    for (const f of files) form.append('files', f)
    return postForm<CustomerAttachment[]>(`/customers/${id}/documents`, form)
  },
  deleteCustomerDocument: (docId: string) =>
    del(`/customers/documents/${docId}`),
  /** Descarga autenticada (lleva X-Tenant-Id/Bearer, que un <a> no enviaría). */
  downloadCustomerDocument: async (docId: string, filename: string) => {
    const res = await fetch(`${BASE}/customers/documents/${docId}/download`, {
      headers: baseHeaders(),
    })
    if (!res.ok) throw await toError(res, `/customers/documents/${docId}`)
    const url = URL.createObjectURL(await res.blob())
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  },
  dashboardAlerts: () =>
    get<{ data: DashboardAlertItem[] }>('/dashboard/alerts'),
  acquisitionBySource: () =>
    get<{ total: number; data: AcquisitionSource[] }>(
      '/dashboard/acquisition-by-source',
    ),
  alerts: (teamId?: string) =>
    get<Paginated<ApiAlert>>('/alerts', { teamId, limit: '20' }),
  agentPerformance: (teamId?: string) =>
    get<Paginated<AgentPerformance>>('/dashboard/agent-performance', {
      teamId,
      limit: '50',
    }),
  dailyKpis: () => get<DailyKpis>('/dashboard/daily-kpis'),
  aiImpact: () => get<AiImpact>('/dashboard/ai-impact'),
  customerPortfolio: (filters?: PortfolioFilters) =>
    get<CustomerPortfolio>('/dashboard/customer-portfolio', {
      ...filters,
      limit: '50',
    }),
  leadsKpis: () => get<LeadsKpis>('/dashboard/leads-kpis'),
  channelFunnel: () => get<ChannelFunnel>('/dashboard/channel-funnel'),
  queueHealth: () => get<QueueHealth[]>('/dashboard/queue-health'),
  hotLeadsUncontacted: () =>
    get<Paginated<HotLead>>('/dashboard/hot-leads-uncontacted', { limit: '20' }),
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
