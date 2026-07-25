/**
 * Cliente tipado del backend de dominio (NestJS) — proxy nginx en `/api/v1`.
 * Todas las lecturas aceptan scoping multitenant vía `teamId` donde el
 * backend lo soporta (users, alerts, dashboard/agent-performance).
 */

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

export type LeadsKpis = {
  avgFirstResponseHours: number | null
  avgCustomerResponseMinutes: number | null
  unresponsiveOver48h: { total: number; stale: number; pct: number }
  intentDistribution: { intent: string; count: number }[]
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
    createdAt: string
  }
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
  const headers: Record<string, string> = { Accept: 'application/json' }
  const tenant = getStoredTenantId()
  if (tenant) headers['X-Tenant-Id'] = tenant
  const res = await fetch(`${BASE}${path}${suffix}`, { headers })
  if (!res.ok) throw new Error(`API ${path} → HTTP ${res.status}`)
  return res.json() as Promise<T>
}

export const api = {
  teams: () => get<Paginated<Team>>('/teams', { limit: '50' }),
  users: (teamId?: string) =>
    get<Paginated<TeamUser>>('/users', { teamId, limit: '100' }),
  leads: () => get<Paginated<ApiLead>>('/leads', { limit: '100' }),
  customers: () => get<Paginated<ApiCustomer>>('/customers', { limit: '100' }),
  customerFull: (id: string) => get<CustomerFull>(`/customers/${id}/full`),
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
