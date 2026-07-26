/**
 * Cartera de Clientes 360° del gerente: totales del tenant, filtros
 * (búsqueda, interés, estado, producto, riesgo) y tabla por cliente con el
 * nivel de riesgo explicable que calcula el backend
 * (GET /dashboard/customer-portfolio) a partir del motor de scoring de leads,
 * pólizas vigentes y triage de reclamos.
 */
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { Card } from '../../components/ui/Card'
import { Chip } from '../../components/ui/Chip'
import { Icon } from '../../components/ui/Icon'
import {
  api,
  formatCop,
  type CustomerPortfolio as PortfolioData,
  type PortfolioCustomer,
} from '../../lib/api'
import { useTenant } from '../../tenant/TenantContext'
import { CustomerDetailDrawer } from '../agent/CustomerDetailDrawer'
import { CustomerFormModal } from './CustomerFormModal'

const STATUS_LABEL: Record<string, string> = {
  NUEVO: 'Nuevo',
  CONTACTADO: 'Contactado',
  COTIZADO: 'Cotizado',
  NEGOCIACION: 'Negociación',
  CERRADO_GANADO: 'Ganado',
  CERRADO_PERDIDO: 'Perdido',
}

const INTENT_META: Record<string, { label: string; tone: 'hot' | 'warm' | 'cold' }> = {
  CALIENTE: { label: 'Caliente', tone: 'hot' },
  TIBIO: { label: 'Tibio', tone: 'warm' },
  FRIO: { label: 'Frío', tone: 'cold' },
}

const CHANNEL_LABEL: Record<string, string> = {
  WEB_INTEREST: 'Interés web',
  WEB_CHAT: 'Chat web',
  WHATSAPP: 'WhatsApp',
  EMAIL: 'Email',
  VOICE_CALL: 'Llamada',
}

const RISK_META: Record<
  string,
  { label: string; chip: string; icon: string }
> = {
  alto: {
    label: 'Alto',
    chip: 'bg-error-container text-on-error-container',
    icon: 'warning',
  },
  medio: {
    label: 'Medio',
    chip: 'bg-amber-cta/20 text-on-secondary-fixed-variant',
    icon: 'error_outline',
  },
  bajo: {
    label: 'Bajo',
    chip: 'bg-primary/10 text-primary',
    icon: 'check_circle',
  },
}

const PRODUCT_LABEL: Record<string, string> = {
  VIDA: 'Vida',
  AUTO: 'Auto',
  SALUD: 'Salud',
}

type Filters = {
  search: string
  intent: string
  status: string
  insuranceType: string
  risk: string
}

const EMPTY_FILTERS: Filters = {
  search: '',
  intent: '',
  status: '',
  insuranceType: '',
  risk: '',
}

const selectClass =
  'rounded-lg border border-outline-variant bg-surface-container-lowest px-3 py-2 text-sm text-on-surface outline-none focus:border-primary'

function SummaryTile({
  icon,
  label,
  value,
  hint,
  tone = 'default',
}: {
  icon: string
  label: string
  value: string
  hint?: string
  tone?: 'default' | 'alert'
}) {
  return (
    <div
      className={`flex flex-col gap-0.5 rounded-lg border p-3 ${
        tone === 'alert'
          ? 'border-error/30 bg-error-container/30'
          : 'border-outline-variant bg-surface-container-lowest'
      }`}
    >
      <span className="flex items-center gap-1.5 text-[11px] font-medium text-on-surface-variant">
        <Icon
          name={icon}
          className={`text-[15px] ${tone === 'alert' ? 'text-error' : 'text-primary'}`}
        />
        {label}
      </span>
      <span className="text-lg font-bold text-on-surface tabular-nums xs:text-xl">
        {value}
      </span>
      {hint && <span className="text-[10px] text-outline">{hint}</span>}
    </div>
  )
}

function PriorityBar({ score }: { score: number }) {
  const pct = Math.min(100, Math.round(score / 10))
  const color =
    score > 700 ? 'bg-error' : score >= 400 ? 'bg-amber-cta' : 'bg-primary/60'
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-14 overflow-hidden rounded-full bg-surface-variant">
        <div className={`h-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs font-bold text-on-surface">{score}</span>
    </div>
  )
}

function CustomerRow({
  c,
  onSelect,
  onEdit,
}: {
  c: PortfolioCustomer
  onSelect: (c: PortfolioCustomer) => void
  onEdit: (c: PortfolioCustomer) => void
}) {
  const intent = c.lead ? INTENT_META[c.lead.intent] : null
  const risk = RISK_META[c.risk.level]
  const channel = c.lead?.highestChannel
    ? (CHANNEL_LABEL[c.lead.highestChannel] ?? c.lead.highestChannel)
    : null
  return (
    <tr
      onClick={() => onSelect(c)}
      className="cursor-pointer align-top transition-colors hover:bg-mist-white"
    >
      <td className="px-4 py-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="text-sm font-bold text-on-surface">
              {c.fullName ?? 'Sin nombre'}
            </p>
            <p className="text-[11px] text-on-surface-variant">
              {[c.phone, c.city].filter(Boolean).join(' · ') || c.email || '—'}
            </p>
            {c.lead?.agentName && (
              <p className="mt-0.5 flex items-center gap-1 text-[10px] text-outline">
                <Icon name="badge" className="text-[12px]" />
                {c.lead.agentName}
              </p>
            )}
          </div>
          <button
            type="button"
            aria-label="Editar cliente"
            title="Editar cliente"
            onClick={(e) => {
              e.stopPropagation()
              onEdit(c)
            }}
            className="shrink-0 rounded-md p-1 text-outline transition-colors hover:bg-primary/10 hover:text-primary"
          >
            <Icon name="edit" className="text-[16px]" />
          </button>
        </div>
      </td>
      <td className="px-4 py-3">
        {c.lead ? (
          <div className="flex flex-col items-start gap-1">
            {intent && <Chip tone={intent.tone}>{intent.label}</Chip>}
            <span className="text-[11px] text-on-surface-variant">
              {c.lead.insuranceType
                ? (PRODUCT_LABEL[c.lead.insuranceType] ?? c.lead.insuranceType)
                : 'Sin producto'}
              {' · '}
              {STATUS_LABEL[c.lead.status] ?? c.lead.status}
            </span>
          </div>
        ) : (
          <span className="text-[11px] text-outline">Sin lead</span>
        )}
      </td>
      <td className="px-4 py-3">
        {c.lead ? <PriorityBar score={c.lead.priorityScore} /> : '—'}
      </td>
      <td className="px-4 py-3">
        <span
          title={c.risk.factors.join('\n')}
          className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-label-sm font-bold ${risk.chip}`}
        >
          <Icon name={risk.icon} className="text-[13px]" />
          {risk.label}
        </span>
        {c.risk.factors[0] && (
          <p className="mt-1 max-w-44 text-[10px] leading-tight text-outline">
            {c.risk.factors[0]}
            {c.risk.factors.length > 1 && ` (+${c.risk.factors.length - 1})`}
          </p>
        )}
      </td>
      <td className="px-4 py-3 text-[11px] text-on-surface-variant">
        {channel ?? '—'}
        {c.calls.total > 0 && (
          <p className="text-[10px] text-outline">
            {c.calls.total} sesión(es) IA
          </p>
        )}
      </td>
      <td className="px-4 py-3">
        <p className="text-sm font-bold text-on-surface">
          {c.policies.active > 0 ? formatCop(c.policies.monthlyPremiumCop) : '—'}
        </p>
        <p className="text-[10px] text-outline">
          {c.policies.active} vigente(s)
        </p>
      </td>
      <td className="px-4 py-3">
        {c.claims.total > 0 ? (
          <div className="flex flex-col gap-0.5">
            <span className="text-sm text-on-surface">
              {c.claims.open} abierto(s)
            </span>
            {c.claims.maxFraudScore != null && c.claims.maxFraudScore >= 0.5 && (
              <span className="inline-flex items-center gap-1 text-[10px] font-bold text-error">
                <Icon name="report" filled className="text-[12px]" />
                fraude {c.claims.maxFraudScore.toFixed(2)}
              </span>
            )}
          </div>
        ) : (
          <span className="text-[11px] text-outline">—</span>
        )}
      </td>
      <td className="px-4 py-3 text-[11px] text-on-surface-variant">
        {c.lead?.hoursSinceResponse != null ? (
          <span
            className={
              c.lead.hoursSinceResponse > 48 ? 'font-bold text-error' : ''
            }
          >
            hace {c.lead.hoursSinceResponse} h
          </span>
        ) : (
          '—'
        )}
        {c.lead?.uncontacted && (
          <p className="text-[10px] font-bold text-error">sin contactar</p>
        )}
      </td>
    </tr>
  )
}

/** Campo etiqueta+valor para el layout de card en celular. */
function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <p className="text-[10px] font-semibold tracking-wide text-on-surface-variant uppercase">
        {label}
      </p>
      <div className="mt-0.5 text-xs text-on-surface">{children}</div>
    </div>
  )
}

/**
 * Versión en tarjeta apilada (celular) de una fila de cartera: la misma
 * información que `CustomerRow` pero como bloque vertical con etiquetas, sin
 * scroll horizontal. Se muestra por debajo de `md`; la tabla toma el relevo
 * en pantallas anchas.
 */
function CustomerCard({
  c,
  onSelect,
  onEdit,
}: {
  c: PortfolioCustomer
  onSelect: (c: PortfolioCustomer) => void
  onEdit: (c: PortfolioCustomer) => void
}) {
  const intent = c.lead ? INTENT_META[c.lead.intent] : null
  const risk = RISK_META[c.risk.level]
  const channel = c.lead?.highestChannel
    ? (CHANNEL_LABEL[c.lead.highestChannel] ?? c.lead.highestChannel)
    : null
  return (
    <div
      onClick={() => onSelect(c)}
      className="cursor-pointer rounded-xl border border-outline-variant bg-surface-container-lowest p-4 shadow-sm transition-colors hover:border-primary/40"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-bold text-on-surface">
            {c.fullName ?? 'Sin nombre'}
          </p>
          <p className="text-[11px] break-words text-on-surface-variant">
            {[c.phone, c.city].filter(Boolean).join(' · ') || c.email || '—'}
          </p>
          {c.lead?.agentName && (
            <p className="mt-0.5 flex items-center gap-1 text-[10px] text-outline">
              <Icon name="badge" className="text-[12px]" />
              {c.lead.agentName}
            </p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <span
            title={c.risk.factors.join('\n')}
            className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-label-sm font-bold ${risk.chip}`}
          >
            <Icon name={risk.icon} className="text-[13px]" />
            {risk.label}
          </span>
          <button
            type="button"
            aria-label="Editar cliente"
            onClick={(e) => {
              e.stopPropagation()
              onEdit(c)
            }}
            className="rounded-md p-1 text-outline transition-colors hover:bg-primary/10 hover:text-primary"
          >
            <Icon name="edit" className="text-[16px]" />
          </button>
        </div>
      </div>
      {c.risk.factors[0] && (
        <p className="mt-1.5 text-[10px] leading-tight text-outline">
          {c.risk.factors[0]}
          {c.risk.factors.length > 1 && ` (+${c.risk.factors.length - 1})`}
        </p>
      )}
      <div className="mt-3 grid grid-cols-2 gap-x-3 gap-y-3">
        <Field label="Interés / Lead">
          {c.lead ? (
            <div className="flex flex-col items-start gap-1">
              {intent && <Chip tone={intent.tone}>{intent.label}</Chip>}
              <span className="text-[11px] text-on-surface-variant">
                {c.lead.insuranceType
                  ? (PRODUCT_LABEL[c.lead.insuranceType] ?? c.lead.insuranceType)
                  : 'Sin producto'}
                {' · '}
                {STATUS_LABEL[c.lead.status] ?? c.lead.status}
              </span>
            </div>
          ) : (
            <span className="text-[11px] text-outline">Sin lead</span>
          )}
        </Field>
        <Field label="Prioridad">
          {c.lead ? <PriorityBar score={c.lead.priorityScore} /> : '—'}
        </Field>
        <Field label="Canal">
          {channel ?? '—'}
          {c.calls.total > 0 && (
            <span className="block text-[10px] text-outline">
              {c.calls.total} sesión(es) IA
            </span>
          )}
        </Field>
        <Field label="Prima mensual">
          <span className="font-bold text-on-surface">
            {c.policies.active > 0 ? formatCop(c.policies.monthlyPremiumCop) : '—'}
          </span>
          <span className="block text-[10px] text-outline">
            {c.policies.active} vigente(s)
          </span>
        </Field>
        <Field label="Reclamos">
          {c.claims.total > 0 ? (
            <div className="flex flex-col gap-0.5">
              <span>{c.claims.open} abierto(s)</span>
              {c.claims.maxFraudScore != null &&
                c.claims.maxFraudScore >= 0.5 && (
                  <span className="inline-flex items-center gap-1 text-[10px] font-bold text-error">
                    <Icon name="report" filled className="text-[12px]" />
                    fraude {c.claims.maxFraudScore.toFixed(2)}
                  </span>
                )}
            </div>
          ) : (
            <span className="text-outline">—</span>
          )}
        </Field>
        <Field label="Últ. respuesta">
          {c.lead?.hoursSinceResponse != null ? (
            <span
              className={
                c.lead.hoursSinceResponse > 48 ? 'font-bold text-error' : ''
              }
            >
              hace {c.lead.hoursSinceResponse} h
            </span>
          ) : (
            '—'
          )}
          {c.lead?.uncontacted && (
            <span className="block text-[10px] font-bold text-error">
              sin contactar
            </span>
          )}
        </Field>
      </div>
    </div>
  )
}

export function CustomerPortfolio() {
  const { teamId } = useTenant()
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS)
  const [search, setSearch] = useState('')
  const [data, setData] = useState<PortfolioData | null>(null)
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<PortfolioCustomer | null>(null)
  const [formState, setFormState] = useState<{
    mode: 'create' | 'edit'
    id?: string
  } | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  // La búsqueda escribe con debounce sobre los filtros reales.
  useEffect(() => {
    const t = setTimeout(
      () => setFilters((f) => (f.search === search ? f : { ...f, search })),
      300,
    )
    return () => clearTimeout(t)
  }, [search])

  useEffect(() => {
    let alive = true
    setLoading(true)
    api
      .customerPortfolio({
        search: filters.search || undefined,
        intent: filters.intent || undefined,
        status: filters.status || undefined,
        insuranceType: filters.insuranceType || undefined,
        risk: filters.risk || undefined,
      })
      .then((d) => alive && setData(d))
      .catch(() => alive && setData(null))
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [filters, teamId, reloadKey])

  const refetch = () => setReloadKey((k) => k + 1)

  const summary = data?.summary
  const hasActiveFilters = useMemo(
    () => Object.values(filters).some(Boolean),
    [filters],
  )

  if (!data && !loading) return null

  return (
    <Card className="rounded-lg border border-outline-variant">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-outline-variant p-5">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-bold text-on-surface">
            <Icon name="diversity_3" className="text-primary" />
            Cartera de Clientes
          </h2>
          <p className="text-xs text-on-surface-variant">
            Todo lo que el sistema sabe de cada cliente: interés, prioridad,
            pólizas, reclamos y riesgo
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs text-on-surface-variant">
          {summary && (
            <>
              <Chip tone="hot">{summary.byRisk.alto} riesgo alto</Chip>
              <Chip tone="amber">{summary.byRisk.medio} medio</Chip>
              <Chip tone="success">{summary.byRisk.bajo} bajo</Chip>
            </>
          )}
          <button
            type="button"
            onClick={() => setFormState({ mode: 'create' })}
            className="inline-flex items-center gap-1.5 rounded-full bg-primary px-3.5 py-2 text-label-md font-semibold text-on-primary shadow-sm transition-transform hover:scale-[1.03]"
          >
            <Icon name="person_add" filled className="text-[18px]" />
            Nuevo cliente
          </button>
        </div>
      </div>

      {summary && (
        <div className="grid grid-cols-2 gap-3 border-b border-outline-variant p-5 md:grid-cols-3 xl:grid-cols-6">
          <SummaryTile
            icon="groups"
            label="Clientes"
            value={summary.totalCustomers.toLocaleString('es-CO')}
            hint={`${summary.openLeads} con lead abierto`}
          />
          <SummaryTile
            icon="payments"
            label="Prima mensual activa"
            value={formatCop(summary.monthlyPremiumCop)}
            hint={`${summary.activePolicies} pólizas vigentes`}
          />
          <SummaryTile
            icon="local_fire_department"
            label="Leads calientes"
            value={summary.byIntent.caliente.toLocaleString('es-CO')}
            hint={`${summary.byIntent.tibio} tibios · ${summary.byIntent.frio} fríos`}
          />
          <SummaryTile
            icon="phone_missed"
            label="Calientes sin contactar"
            value={summary.hotUncontacted.toLocaleString('es-CO')}
            tone={summary.hotUncontacted > 0 ? 'alert' : 'default'}
            hint="Requieren acción hoy"
          />
          <SummaryTile
            icon="hourglass_bottom"
            label="Sin respuesta +48h"
            value={summary.unresponsive48h.toLocaleString('es-CO')}
            tone={summary.unresponsive48h > 0 ? 'alert' : 'default'}
            hint="Riesgo de enfriarse"
          />
          <SummaryTile
            icon="health_and_safety"
            label="Reclamos abiertos"
            value={summary.openClaims.toLocaleString('es-CO')}
            tone={summary.fraudSuspects > 0 ? 'alert' : 'default'}
            hint={
              summary.fraudSuspects > 0
                ? `${summary.fraudSuspects} con alerta de fraude`
                : 'Sin alertas de fraude'
            }
          />
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2 border-b border-outline-variant p-4">
        <label className="relative min-w-52 flex-1">
          <Icon
            name="search"
            className="absolute top-1/2 left-3 -translate-y-1/2 text-[18px] text-on-surface-variant"
          />
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar por nombre, teléfono, documento…"
            className="w-full rounded-lg border border-outline-variant bg-surface-container-lowest py-2 pr-3 pl-10 text-sm text-on-surface outline-none focus:border-primary"
          />
        </label>
        <select
          value={filters.intent}
          onChange={(e) => setFilters({ ...filters, intent: e.target.value })}
          className={selectClass}
          aria-label="Filtrar por interés"
        >
          <option value="">Interés: todos</option>
          <option value="CALIENTE">🔥 Caliente</option>
          <option value="TIBIO">Tibio</option>
          <option value="FRIO">Frío</option>
        </select>
        <select
          value={filters.risk}
          onChange={(e) => setFilters({ ...filters, risk: e.target.value })}
          className={selectClass}
          aria-label="Filtrar por riesgo"
        >
          <option value="">Riesgo: todos</option>
          <option value="alto">Alto</option>
          <option value="medio">Medio</option>
          <option value="bajo">Bajo</option>
        </select>
        <select
          value={filters.status}
          onChange={(e) => setFilters({ ...filters, status: e.target.value })}
          className={selectClass}
          aria-label="Filtrar por estado"
        >
          <option value="">Estado: todos</option>
          {Object.entries(STATUS_LABEL).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <select
          value={filters.insuranceType}
          onChange={(e) =>
            setFilters({ ...filters, insuranceType: e.target.value })
          }
          className={selectClass}
          aria-label="Filtrar por producto"
        >
          <option value="">Producto: todos</option>
          <option value="VIDA">Vida</option>
          <option value="AUTO">Auto</option>
          <option value="SALUD">Salud</option>
        </select>
        {hasActiveFilters && (
          <button
            type="button"
            onClick={() => {
              setSearch('')
              setFilters(EMPTY_FILTERS)
            }}
            className="flex items-center gap-1 rounded-lg px-3 py-2 text-sm font-semibold text-primary hover:bg-primary/10"
          >
            <Icon name="filter_alt_off" className="text-[18px]" />
            Limpiar
          </button>
        )}
      </div>

      {/* Desktop (md+): tabla completa con scroll horizontal de respaldo */}
      <div className="hidden overflow-x-auto md:block">
        <table className="w-full text-left">
          <thead>
            <tr className="bg-surface-container-low/50">
              {[
                'Cliente',
                'Interés / Lead',
                'Prioridad',
                'Riesgo',
                'Canal',
                'Prima mensual',
                'Reclamos',
                'Últ. respuesta',
              ].map((h) => (
                <th
                  key={h}
                  className="px-4 py-3 text-xs font-semibold tracking-wider text-on-surface-variant uppercase"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-outline-variant">
            {(data?.data ?? []).map((c) => (
              <CustomerRow
                key={c.customerId}
                c={c}
                onSelect={setSelected}
                onEdit={(cust) =>
                  setFormState({ mode: 'edit', id: cust.customerId })
                }
              />
            ))}
          </tbody>
        </table>
      </div>

      {/* Móvil (<md): cada cliente como tarjeta apilada, sin scroll lateral */}
      <div className="flex flex-col gap-3 p-4 md:hidden">
        {(data?.data ?? []).map((c) => (
          <CustomerCard
            key={c.customerId}
            c={c}
            onSelect={setSelected}
            onEdit={(cust) => setFormState({ mode: 'edit', id: cust.customerId })}
          />
        ))}
      </div>

      {loading && (
        <p className="p-6 text-center text-sm text-on-surface-variant">
          Cargando cartera…
        </p>
      )}
      {!loading && data && data.data.length === 0 && (
        <p className="p-6 text-center text-sm text-on-surface-variant">
          {hasActiveFilters
            ? 'Ningún cliente coincide con los filtros.'
            : 'Este equipo aún no tiene clientes registrados.'}
        </p>
      )}
      {data && data.meta.total > data.data.length && (
        <p className="border-t border-outline-variant px-5 py-3 text-xs text-on-surface-variant">
          Mostrando {data.data.length} de {data.meta.total} clientes
        </p>
      )}

      <CustomerDetailDrawer
        customerId={selected?.customerId ?? null}
        name={selected?.fullName ?? undefined}
        leadId={selected?.lead?.id}
        intent={selected?.lead ? INTENT_META[selected.lead.intent]?.tone : undefined}
        intentLabel={
          selected?.lead ? INTENT_META[selected.lead.intent]?.label : undefined
        }
        open={selected != null}
        onClose={() => setSelected(null)}
      />

      {formState && (
        <CustomerFormModal
          mode={formState.mode}
          customerId={formState.id}
          onClose={() => setFormState(null)}
          onSaved={refetch}
        />
      )}
    </Card>
  )
}
