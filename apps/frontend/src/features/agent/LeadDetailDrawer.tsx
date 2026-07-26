/**
 * Drawer de detalle del vendedor: expediente 360° del cliente. Con backend
 * disponible carga GET /customers/:id/full y muestra TODO lo que el sistema
 * sabe: datos personales, perfil IA (hijos, etapa de vida, riesgo,
 * propensión, necesidades), datos declarados en la conversación, lead con su
 * historial, cotizaciones, pólizas, reclamos y transcripciones de sesiones
 * IA. Sin backend (leads mock) degrada al contenido demo de siempre.
 */
import { useEffect, useState, type ReactNode } from 'react'
import { Icon } from '../../components/ui/Icon'
import { Button } from '../../components/ui/Button'
import { Chip } from '../../components/ui/Chip'
import type { Lead } from '../../data/mock/types'
import {
  api,
  formatCop,
  type AiPerfil,
  type ConversationTurn,
  type CustomerDocument,
  type CustomerFull,
  type FullAiCall,
} from '../../lib/api'

type Props = {
  lead: Lead | null
  open: boolean
  onClose: () => void
}

const STATUS_LABEL: Record<string, string> = {
  NUEVO: 'Nuevo',
  CONTACTADO: 'Contactado',
  COTIZADO: 'Cotizado',
  NEGOCIACION: 'Negociación',
  CERRADO_GANADO: 'Cerrado ganado',
  CERRADO_PERDIDO: 'Cerrado perdido',
  BORRADOR: 'Borrador',
  ENVIADA: 'Enviada',
  ACEPTADA: 'Aceptada',
  RECHAZADA: 'Rechazada',
  VENCIDA: 'Vencida',
  VIGENTE: 'Vigente',
  CANCELADA: 'Cancelada',
  SUSPENDIDA: 'Suspendida',
  REPORTADO: 'Reportado',
  EN_REVISION: 'En revisión',
  DOCS_PENDIENTES: 'Docs pendientes',
  APROBADO: 'Aprobado',
  RECHAZADO: 'Rechazado',
  PAGADO: 'Pagado',
  EN_CURSO: 'En curso',
  COMPLETADA: 'Completada',
  ABANDONADA: 'Abandonada',
  TRANSFERIDA_HUMANO: 'Transferida a humano',
  FALLIDA: 'Fallida',
}

const CHANNEL_LABEL: Record<string, string> = {
  WEB_INTEREST: 'Interés web',
  WEB_CHAT: 'Chat web',
  WHATSAPP: 'WhatsApp',
  EMAIL: 'Email',
  VOICE_CALL: 'Llamada',
}

const EVENT_LABEL: Record<string, { label: string; icon: string }> = {
  LLAMADA_SALIENTE: { label: 'Llamada saliente', icon: 'call' },
  WHATSAPP: { label: 'WhatsApp', icon: 'chat' },
  EMAIL: { label: 'Email', icon: 'mail' },
  REUNION: { label: 'Reunión', icon: 'event' },
  NOTA: { label: 'Nota', icon: 'sticky_note_2' },
  CAMBIO_ESTADO: { label: 'Cambio de estado', icon: 'swap_horiz' },
  REASIGNACION: { label: 'Reasignación', icon: 'person_pin' },
}

const ETAPA_LABEL: Record<string, string> = {
  joven_independiente: 'Joven independiente',
  joven_con_familia: 'Joven con familia',
  familia_consolidada: 'Familia consolidada',
  adulto_establecido: 'Adulto establecido',
  adulto_maduro: 'Adulto maduro',
  adulto_mayor: 'Adulto mayor',
}

/** Etiquetas del intake (datos declarados) que se muestran, en este orden. */
const INTAKE_FIELDS: { key: string; label: string; format?: (v: unknown) => string }[] = [
  { key: 'afiliado_colsubsidio', label: 'Afiliado a Colsubsidio' },
  { key: 'estado_civil', label: 'Estado civil' },
  { key: 'dependientes', label: 'Hijos / dependientes' },
  { key: 'ocupacion', label: 'Ocupación' },
  { key: 'actividad_economica', label: 'Actividad económica' },
  {
    key: 'ingresos_mensuales',
    label: 'Ingresos mensuales',
    format: (v) => formatCop(Number(v)),
  },
  { key: 'sexo', label: 'Sexo' },
  { key: 'fecha_nacimiento', label: 'Nacimiento' },
  { key: 'beneficiarios', label: 'Beneficiarios' },
  { key: 'fumador', label: 'Fumador' },
  { key: 'enfermedades', label: 'Enfermedades' },
  { key: 'preexistencias', label: 'Preexistencias' },
  { key: 'deportes_riesgo', label: 'Deportes de riesgo' },
  { key: 'consume_alcohol', label: 'Consume alcohol' },
  { key: 'origen_fondos', label: 'Origen de fondos' },
  { key: 'marca', label: 'Vehículo' },
  { key: 'placa', label: 'Placa' },
  { key: 'modelo_anio', label: 'Modelo (año)' },
  { key: 'tenencia', label: 'Tenencia' },
]

function fmtDate(iso: string | null | undefined, withTime = false): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleDateString('es-CO', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    ...(withTime && { hour: '2-digit', minute: '2-digit' }),
  })
}

function boolText(v: unknown): string {
  if (typeof v === 'boolean') return v ? 'Sí' : 'No'
  return String(v)
}

function Section({
  icon,
  title,
  badge,
  children,
  defaultOpen = false,
}: {
  icon: string
  title: string
  badge?: string
  children: ReactNode
  defaultOpen?: boolean
}) {
  return (
    <details
      className="group rounded-xl border border-outline-variant/70 bg-white"
      open={defaultOpen}
    >
      <summary className="flex cursor-pointer items-center gap-2 rounded-xl px-4 py-3 select-none hover:bg-surface-container-low">
        <Icon name={icon} className="text-[18px] text-primary" />
        <span className="text-sm font-bold text-on-surface">{title}</span>
        {badge && (
          <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-bold text-primary">
            {badge}
          </span>
        )}
        <Icon
          name="expand_more"
          className="ml-auto text-[18px] text-outline transition-transform group-open:rotate-180"
        />
      </summary>
      <div className="border-t border-outline-variant/60 p-4">{children}</div>
    </details>
  )
}

function Field({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="rounded-lg bg-surface-container-low p-3">
      <p className="mb-0.5 text-[10px] font-bold tracking-wide text-outline uppercase">
        {label}
      </p>
      <p className="text-sm font-semibold break-words text-on-surface">{value}</p>
    </div>
  )
}

function AiProfileSection({ perfil }: { perfil: AiPerfil }) {
  const propension =
    perfil.propension_compra != null
      ? Math.round(perfil.propension_compra * 100)
      : null
  return (
    <div className="space-y-4">
      {perfil.resumen_perfil && (
        <p className="rounded-lg border border-primary/20 bg-primary-fixed/20 p-3 text-sm leading-relaxed text-on-surface">
          {perfil.resumen_perfil}
        </p>
      )}
      <div className="grid grid-cols-2 gap-2">
        {perfil.edad != null && <Field label="Edad" value={`${perfil.edad} años`} />}
        {perfil.dependientes != null && (
          <Field
            label="Hijos / dependientes"
            value={
              perfil.dependientes > 0 ? `${perfil.dependientes}` : 'Sin dependientes'
            }
          />
        )}
        {perfil.etapa_vida && (
          <Field
            label="Etapa de vida"
            value={ETAPA_LABEL[perfil.etapa_vida] ?? perfil.etapa_vida}
          />
        )}
        {perfil.segmento_riesgo && (
          <Field
            label="Segmento de riesgo"
            value={
              <span className="capitalize">
                {perfil.segmento_riesgo}
                {perfil.segmento_riesgo_motivos?.length
                  ? ` (${perfil.segmento_riesgo_motivos.join(', ')})`
                  : ''}
              </span>
            }
          />
        )}
        {perfil.nivel_capacidad && (
          <Field
            label="Capacidad de pago"
            value={
              <span className="capitalize">
                {perfil.nivel_capacidad}
                {perfil.capacidad_pago_mensual_cop
                  ? ` · ${formatCop(perfil.capacidad_pago_mensual_cop)}/mes`
                  : ''}
              </span>
            }
          />
        )}
        {propension != null && (
          <div className="rounded-lg bg-surface-container-low p-3">
            <p className="mb-1 text-[10px] font-bold tracking-wide text-outline uppercase">
              Propensión de compra
            </p>
            <div className="flex items-center gap-2">
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-variant">
                <div
                  className={`h-full ${propension >= 70 ? 'bg-primary' : propension >= 45 ? 'bg-amber-cta' : 'bg-error'}`}
                  style={{ width: `${propension}%` }}
                />
              </div>
              <span className="text-sm font-bold text-on-surface">{propension}%</span>
            </div>
          </div>
        )}
      </div>
      {(perfil.banderas?.length ?? 0) > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {perfil.banderas!.map((b) => (
            <Chip key={b} tone="amber">
              <Icon name="flag" className="text-[12px]" />
              {b.replaceAll('_', ' ')}
            </Chip>
          ))}
        </div>
      )}
      {(perfil.necesidades_detectadas?.length ?? 0) > 0 && (
        <div>
          <p className="mb-2 text-xs font-bold text-on-surface-variant">
            Necesidades detectadas
          </p>
          <ul className="space-y-2">
            {perfil.necesidades_detectadas!.map((n) => (
              <li key={n.tipo} className="flex items-start gap-2 text-xs">
                <Chip tone={n.prioridad === 'alta' ? 'hot' : n.prioridad === 'media' ? 'warm' : 'neutral'}>
                  {n.tipo}
                </Chip>
                <span className="pt-1 text-on-surface-variant">{n.razon}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {(perfil.productos_recomendados?.length ?? 0) > 0 && (
        <div>
          <p className="mb-2 text-xs font-bold text-on-surface-variant">
            Productos recomendados por la IA
          </p>
          <div className="flex flex-wrap gap-1.5">
            {perfil.productos_recomendados!.map((p) => (
              <Chip key={p.producto_id ?? p.tipo} tone="success">
                <Icon name="verified" className="text-[12px]" />
                {p.producto_id ?? p.tipo}
              </Chip>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

const SEXO_LABEL: Record<string, string> = {
  F: 'Mujer',
  M: 'Hombre',
  FEMENINO: 'Mujer',
  MASCULINO: 'Hombre',
  MUJER: 'Mujer',
  HOMBRE: 'Hombre',
}

const CHANNEL_CHAT_LABEL: Record<string, string> = {
  web: 'Chat web',
  whatsapp: 'WhatsApp',
  voz: 'Nota de voz',
}

function str(v: unknown): string | null {
  if (v == null) return null
  const s = String(v).trim()
  return s === '' ? null : s
}

/** Deriva si el cliente está en pareja a partir del estado civil declarado. */
function parejaFromEstadoCivil(estadoCivil: string | null): string | null {
  if (!estadoCivil) return null
  const s = estadoCivil.toLowerCase()
  if (/(casad|uni[óo]n|pareja|convivi)/.test(s)) return 'En pareja'
  if (/(solter|divorciad|viud|separad)/.test(s)) return 'Sin pareja'
  return null
}

/**
 * Tarjeta destacada de características del cliente. SIEMPRE se muestra cuando
 * hay un cliente cargado: es el lugar fijo donde el asesor/gerente ve de un
 * vistazo edad, pareja, hijos y dónde vive (más género, ocupación y vehículo
 * si existen). Cruza el perfil IA, los datos declarados y el registro del CRM;
 * lo que aún no se conoce se marca "No registrado" para que el campo no
 * desaparezca.
 */
function CharacteristicsCard({
  perfil,
  intake,
  edad,
  city,
  department,
}: {
  perfil: AiPerfil | undefined
  intake: Record<string, unknown> | undefined
  edad: number | null | undefined
  city: string | null | undefined
  department: string | null | undefined
}) {
  const sexoRaw = str(intake?.sexo)
  const sexo = sexoRaw ? (SEXO_LABEL[sexoRaw.toUpperCase()] ?? sexoRaw) : null
  const edadFinal = perfil?.edad ?? edad ?? null
  const ocupacion = str(intake?.ocupacion) ?? str(intake?.actividad_economica)
  const estadoCivil = str(intake?.estado_civil)
  const pareja = parejaFromEstadoCivil(estadoCivil)
  const hijos =
    perfil?.dependientes ??
    (intake?.dependientes != null ? Number(intake.dependientes) : null)
  const ciudad =
    str(intake?.ciudad) ??
    (city && city.toLowerCase() !== 'colombia' ? city : null)
  const ubicacion =
    [ciudad, department].filter(Boolean).join(', ') || null
  const marca = str(intake?.marca)
  const placa = str(intake?.placa)
  const modelo = str(intake?.modelo_anio)

  const NR = 'No registrado'
  // Los 4 campos que el gerente pidió ver siempre + soporte.
  const items: { icon: string; label: string; value: string; known: boolean }[] = [
    {
      icon: 'cake',
      label: 'Edad',
      value: edadFinal != null ? `${edadFinal} años` : NR,
      known: edadFinal != null,
    },
    {
      icon: 'favorite',
      label: 'Pareja',
      value: pareja ?? estadoCivil ?? NR,
      known: pareja != null || estadoCivil != null,
    },
    {
      icon: 'family_restroom',
      label: 'Hijos / dependientes',
      value: hijos != null ? (hijos > 0 ? `${hijos}` : 'Sin hijos') : NR,
      known: hijos != null,
    },
    {
      icon: 'location_on',
      label: 'Dónde vive',
      value: ubicacion ?? NR,
      known: ubicacion != null,
    },
  ]
  if (sexo) items.push({ icon: 'person', label: 'Género', value: sexo, known: true })
  if (ocupacion)
    items.push({ icon: 'work', label: 'Ocupación', value: ocupacion, known: true })
  if (marca)
    items.push({
      icon: 'directions_car',
      label: 'Vehículo',
      value: [marca, modelo ? `(${modelo})` : null].filter(Boolean).join(' '),
      known: true,
    })
  if (placa)
    items.push({
      icon: 'pin',
      label: 'Placa',
      value: placa.toUpperCase(),
      known: true,
    })

  const faltan = items.some((it) => !it.known)

  return (
    <section className="rounded-xl border border-primary/25 bg-primary-fixed/10 p-4">
      <h5 className="mb-3 flex items-center gap-2 text-sm font-bold text-primary">
        <Icon name="badge" className="text-[18px]" />
        Características del cliente
      </h5>
      <div className="grid grid-cols-2 gap-3">
        {items.map((it) => (
          <div key={it.label} className="flex items-start gap-2">
            <Icon
              name={it.icon}
              className={`mt-0.5 text-[18px] ${it.known ? 'text-primary' : 'text-outline'}`}
            />
            <div className="min-w-0">
              <p className="text-[10px] font-bold tracking-wide text-outline uppercase">
                {it.label}
              </p>
              <p
                className={`text-sm font-semibold break-words ${
                  it.known ? 'text-on-surface' : 'text-outline italic'
                }`}
              >
                {it.value}
              </p>
            </div>
          </div>
        ))}
      </div>
      {faltan && (
        <p className="mt-3 flex items-start gap-1.5 rounded-lg bg-surface-container-low p-2 text-[11px] text-on-surface-variant">
          <Icon name="info" className="mt-px text-[14px] text-primary" />
          La IA completa estos datos a medida que conversa con el cliente. Los
          campos "No registrado" aún no se han capturado.
        </p>
      )}
    </section>
  )
}

/**
 * Documentos del cliente: los declarados/firmados que viajan en
 * intake.datos.documentos (descargables por /api/documents/:archivo) más la
 * autorización de habeas data como registro firmado.
 */
function DocumentsSection({
  documents,
  consentData,
  consentAt,
}: {
  documents: CustomerDocument[]
  consentData: boolean
  consentAt: string | null
}) {
  const rows: {
    key: string
    nombre: string
    tipo: string
    firmado: boolean
    fecha?: string
    archivo?: string
  }[] = documents.map((d, i) => ({
    key: `doc-${i}`,
    nombre: d.nombre,
    tipo: d.tipo ?? 'Documento',
    firmado: d.firmado ?? true,
    fecha: d.fecha,
    archivo: d.archivo,
  }))
  if (consentData) {
    rows.unshift({
      key: 'habeas',
      nombre: 'Autorización de tratamiento de datos (Habeas Data)',
      tipo: 'Consentimiento',
      firmado: true,
      fecha: consentAt ?? undefined,
    })
  }
  if (rows.length === 0) return null

  return (
    <Section icon="folder_open" title="Documentos" badge={`${rows.length}`}>
      <ul className="space-y-2">
        {rows.map((d) => (
          <li
            key={d.key}
            className="flex items-center gap-3 rounded-lg border border-outline-variant/60 p-3"
          >
            <Icon
              name={d.firmado ? 'verified' : 'description'}
              className={`text-[22px] ${d.firmado ? 'text-primary' : 'text-outline'}`}
            />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold text-on-surface">
                {d.nombre}
              </p>
              <p className="text-[11px] text-outline">
                {d.tipo}
                {d.firmado ? ' · Firmado' : ''}
                {d.fecha ? ` · ${fmtDate(d.fecha)}` : ''}
              </p>
            </div>
            {d.archivo && (
              <a
                href={`/api/documents/${d.archivo}`}
                target="_blank"
                rel="noreferrer"
                className="flex shrink-0 items-center gap-1 rounded-lg bg-primary/10 px-3 py-1.5 text-xs font-bold text-primary hover:bg-primary/20"
              >
                <Icon name="download" className="text-[16px]" />
                Ver
              </a>
            )}
          </li>
        ))}
      </ul>
    </Section>
  )
}

/** Visor del chat cliente↔IA (web/WhatsApp) — el botón "ver chat" del asesor. */
function ChatViewer({ turns }: { turns: ConversationTurn[] }) {
  const channel = turns.find((t) => t.channel)?.channel
  return (
    <Section
      icon="forum"
      title="Chat con la IA"
      badge={`${turns.length} mensajes`}
    >
      {channel && (
        <p className="mb-3 text-[11px] text-outline">
          Canal: {CHANNEL_CHAT_LABEL[channel] ?? channel}
        </p>
      )}
      <div className="space-y-3 text-sm">
        {turns.map((t, i) => {
          const isClient = t.role === 'cliente'
          return (
            <div
              key={`${t.createdAt}-${i}`}
              className={`flex flex-col gap-0.5 ${isClient ? 'items-end' : ''}`}
            >
              <span className="text-[10px] font-bold text-outline uppercase">
                {isClient ? 'Cliente' : 'Asistente IA'}
                {' · '}
                {fmtDate(t.createdAt, true)}
              </span>
              <p
                className={
                  isClient
                    ? 'ml-6 rounded-2xl rounded-tr-none bg-primary p-2.5 text-on-primary'
                    : 'mr-6 rounded-2xl rounded-tl-none bg-surface-container p-2.5'
                }
              >
                {t.message}
              </p>
            </div>
          )
        })}
      </div>
    </Section>
  )
}

function CallCard({ call }: { call: FullAiCall }) {
  const dur = call.durationSec
    ? `${Math.floor(call.durationSec / 60)}:${String(call.durationSec % 60).padStart(2, '0')} min`
    : null
  return (
    <div className="rounded-lg border border-outline-variant/60 p-3">
      <div className="mb-1 flex flex-wrap items-center gap-2 text-xs">
        <Chip tone="neutral">{CHANNEL_LABEL[call.channel] ?? call.channel}</Chip>
        <span className="text-on-surface-variant">
          {fmtDate(call.startedAt, true)}
        </span>
        {dur && <span className="text-outline">· {dur}</span>}
        <span className="ml-auto text-[10px] font-bold text-outline uppercase">
          {STATUS_LABEL[call.status] ?? call.status}
        </span>
      </div>
      {call.summary && (
        <p className="mb-2 text-xs leading-relaxed text-on-surface-variant">
          {call.summary}
        </p>
      )}
      {call.messages.length > 0 && (
        <details>
          <summary className="cursor-pointer text-xs font-bold text-primary select-none">
            Ver transcripción ({call.messages.length} mensajes)
          </summary>
          <div className="mt-3 space-y-3 text-sm">
            {call.messages.map((m) => (
              <div
                key={m.id}
                className={`flex flex-col gap-0.5 ${m.speaker === 'CLIENTE' ? 'items-end' : ''}`}
              >
                <span className="text-[10px] font-bold text-outline uppercase">
                  {m.speaker === 'IA' ? 'Asistente IA' : 'Cliente'}
                </span>
                <p
                  className={
                    m.speaker === 'IA'
                      ? 'mr-6 rounded-2xl rounded-tl-none bg-surface-container p-2.5'
                      : 'ml-6 rounded-2xl rounded-tr-none bg-primary p-2.5 text-on-primary'
                  }
                >
                  {m.content}
                </p>
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  )
}

export function LeadDetailDrawer({ lead, open, onClose }: Props) {
  const [full, setFull] = useState<CustomerFull | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  useEffect(() => {
    setFull(null)
    if (!open || !lead?.customerId) return
    let alive = true
    setLoading(true)
    api
      .customerFull(lead.customerId)
      .then((d) => alive && setFull(d))
      .catch(() => alive && setFull(null))
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [open, lead?.customerId])

  const customer = full?.customer
  const perfil = full?.aiProfile?.perfil
  const intake = full?.intake?.datos
  const currentLead =
    full?.leads.find((l) => l.id === lead?.id) ?? full?.leads[0] ?? null
  const intakeRows = intake
    ? INTAKE_FIELDS.filter(
        (f) => intake[f.key] != null && String(intake[f.key]).trim() !== '',
      )
    : []
  const hijos =
    perfil?.dependientes ??
    (intake?.dependientes != null ? Number(intake.dependientes) : null)
  const documents = Array.isArray(intake?.documentos)
    ? (intake.documentos as CustomerDocument[])
    : []
  const conversation = full?.conversation ?? []

  return (
    <>
      {/* Scrim: oscurece el fondo y permite cerrar tocando fuera del panel */}
      {open && (
        <div
          className="fixed inset-0 z-20 bg-forest-deep/20 backdrop-blur-[2px]"
          onClick={onClose}
          aria-hidden
        />
      )}
      <aside
        className={`fixed top-0 right-0 z-30 flex h-full w-full max-w-[480px] flex-col overflow-hidden border-l border-outline-variant bg-surface-container-lowest shadow-2xl transition-transform duration-300 ${
          open ? 'translate-x-0' : 'translate-x-full'
        }`}
        aria-hidden={!open}
      >
      <div className="flex items-center justify-between border-b border-outline-variant bg-white p-5">
        <div className="flex items-center gap-3">
          <button
            type="button"
            className="flex size-8 items-center justify-center rounded-full hover:bg-surface-variant"
            onClick={onClose}
            aria-label="Cerrar"
          >
            <Icon name="close" />
          </button>
          <h3 className="text-lg font-bold">Expediente del Cliente</h3>
        </div>
        {loading && (
          <span className="text-xs font-bold text-primary">Cargando…</span>
        )}
      </div>
      {lead ? (
        <>
          <div className="flex-1 space-y-4 overflow-y-auto px-5 py-6">
            {/* Identidad */}
            <section>
              <div className="mb-4 flex items-center gap-4">
                <div className="flex size-14 shrink-0 items-center justify-center rounded-2xl bg-primary text-xl font-black text-on-primary">
                  {lead.initials}
                </div>
                <div className="min-w-0">
                  <h4 className="truncate text-xl font-black text-on-surface">
                    {customer?.fullName ?? lead.name}
                  </h4>
                  <p className="flex items-center gap-1 text-sm text-outline">
                    <Icon name="location_on" className="text-sm" />
                    {[customer?.city ?? lead.location, customer?.department]
                      .filter(Boolean)
                      .join(', ')}
                  </p>
                  <div className="mt-1 flex flex-wrap gap-1.5">
                    {lead.intentLabel && (
                      <Chip tone={lead.intent}>{lead.intentLabel}</Chip>
                    )}
                    {perfil?.etapa_vida && (
                      <Chip tone="neutral">
                        {ETAPA_LABEL[perfil.etapa_vida] ?? perfil.etapa_vida}
                      </Chip>
                    )}
                    {hijos != null && (
                      <Chip tone="neutral">
                        <Icon name="family_restroom" className="text-[12px]" />
                        {hijos > 0 ? `${hijos} hijo(s)` : 'Sin hijos'}
                      </Chip>
                    )}
                  </div>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <Field label="Teléfono" value={customer?.phone ?? lead.phone} />
                <Field label="Correo" value={customer?.email ?? lead.email} />
                {customer?.documentId && (
                  <Field
                    label="Documento"
                    value={`${customer.documentType ?? 'CC'} ${customer.documentId}`}
                  />
                )}
                {(customer?.edad != null || customer?.birthDate) && (
                  <Field
                    label="Edad"
                    value={
                      customer?.edad != null
                        ? `${customer.edad} años (${fmtDate(customer.birthDate)})`
                        : fmtDate(customer?.birthDate)
                    }
                  />
                )}
                {customer && (
                  <Field
                    label="Habeas data"
                    value={
                      customer.consentData
                        ? `Autorizado · ${fmtDate(customer.consentAt)}`
                        : 'Sin autorización'
                    }
                  />
                )}
                {customer && (
                  <Field label="Cliente desde" value={fmtDate(customer.createdAt)} />
                )}
              </div>
            </section>

            {/* Características (género, edad, ocupación, hijos, vehículo) */}
            {customer && (
              <CharacteristicsCard
                perfil={perfil}
                intake={intake}
                edad={customer.edad}
                city={customer.city}
                department={customer.department}
              />
            )}

            {/* Botón "ver chat con la IA" — salta al visor de más abajo */}
            {conversation.length > 0 && (
              <a
                href="#chat-ia"
                className="flex items-center justify-center gap-2 rounded-xl border-2 border-primary/30 bg-primary/5 py-3 text-sm font-bold text-primary transition-colors hover:bg-primary/10"
              >
                <Icon name="forum" className="text-[18px]" />
                Ver chat que tuvo la IA con el cliente ({conversation.length})
              </a>
            )}

            {/* Perfil IA */}
            {perfil ? (
              <Section
                icon="smart_toy"
                title="Perfil IA del cliente"
                badge={full?.aiProfile?.fuente ?? undefined}
                defaultOpen
              >
                <AiProfileSection perfil={perfil} />
              </Section>
            ) : (
              !loading &&
              full && (
                <p className="rounded-lg border border-outline-variant/60 bg-surface-container-low p-3 text-xs text-on-surface-variant">
                  La IA aún no ha perfilado a este cliente (sin conversaciones
                  con datos suficientes).
                </p>
              )
            )}

            {/* Datos declarados en la conversación */}
            {intakeRows.length > 0 && (
              <Section
                icon="assignment_ind"
                title="Datos declarados"
                badge={`${intakeRows.length}`}
              >
                <div className="grid grid-cols-2 gap-2">
                  {intakeRows.map((f) => (
                    <Field
                      key={f.key}
                      label={f.label}
                      value={
                        f.format
                          ? f.format(intake![f.key])
                          : boolText(intake![f.key])
                      }
                    />
                  ))}
                </div>
              </Section>
            )}

            {/* Lead y su historial */}
            {currentLead && (
              <Section
                icon="flag_circle"
                title="Lead y seguimiento"
                badge={STATUS_LABEL[currentLead.status]}
                defaultOpen
              >
                <div className="grid grid-cols-2 gap-2">
                  <Field
                    label="Estado"
                    value={STATUS_LABEL[currentLead.status] ?? currentLead.status}
                  />
                  <Field
                    label="Score de prioridad"
                    value={`${currentLead.priorityScore} / 1000`}
                  />
                  <Field
                    label="Canal"
                    value={
                      currentLead.firstChannel
                        ? `${CHANNEL_LABEL[currentLead.firstChannel] ?? currentLead.firstChannel}${
                            currentLead.highestChannel &&
                            currentLead.highestChannel !== currentLead.firstChannel
                              ? ` → ${CHANNEL_LABEL[currentLead.highestChannel] ?? currentLead.highestChannel}`
                              : ''
                          }`
                        : '—'
                    }
                  />
                  <Field label="Agente" value={currentLead.agentName ?? 'Sin asignar'} />
                  <Field label="Creado" value={fmtDate(currentLead.createdAt, true)} />
                  <Field
                    label="Última respuesta del cliente"
                    value={fmtDate(currentLead.lastCustomerResponseAt, true)}
                  />
                </div>
                {currentLead.lostReason && (
                  <p className="mt-2 rounded-lg bg-error-container/40 p-2 text-xs text-on-error-container">
                    Motivo de pérdida: {currentLead.lostReason}
                  </p>
                )}
                {currentLead.events.length > 0 && (
                  <div className="mt-3">
                    <p className="mb-2 text-xs font-bold text-on-surface-variant">
                      Historial ({currentLead.events.length})
                    </p>
                    <ul className="space-y-2">
                      {currentLead.events.map((ev) => {
                        const meta = EVENT_LABEL[ev.eventType] ?? {
                          label: ev.eventType,
                          icon: 'circle',
                        }
                        return (
                          <li key={ev.id} className="flex items-start gap-2 text-xs">
                            <Icon
                              name={meta.icon}
                              className="mt-0.5 text-[14px] text-primary"
                            />
                            <div className="min-w-0">
                              <p className="font-semibold text-on-surface">
                                {meta.label}
                                <span className="ml-1 font-normal text-outline">
                                  {fmtDate(ev.createdAt, true)}
                                  {ev.agentName ? ` · ${ev.agentName}` : ''}
                                </span>
                              </p>
                              {ev.notes && (
                                <p className="text-on-surface-variant">{ev.notes}</p>
                              )}
                            </div>
                          </li>
                        )
                      })}
                    </ul>
                  </div>
                )}
              </Section>
            )}

            {/* Cotizaciones */}
            {(full?.quotes.length ?? 0) > 0 && (
              <Section
                icon="request_quote"
                title="Cotizaciones"
                badge={`${full!.quotes.length}`}
              >
                <ul className="space-y-2">
                  {full!.quotes.map((q) => (
                    <li
                      key={q.id}
                      className="flex items-center justify-between gap-2 rounded-lg border border-outline-variant/60 p-3 text-sm"
                    >
                      <div className="min-w-0">
                        <p className="truncate font-semibold text-on-surface">
                          {q.product?.name ?? 'Producto'}
                        </p>
                        <p className="text-[11px] text-outline">
                          {fmtDate(q.createdAt)}
                          {q.validUntil ? ` · válida hasta ${fmtDate(q.validUntil)}` : ''}
                        </p>
                      </div>
                      <div className="shrink-0 text-right">
                        <p className="font-bold text-on-surface">
                          {formatCop(q.monthlyPremiumCop)}/mes
                        </p>
                        <span className="text-[10px] font-bold text-primary uppercase">
                          {STATUS_LABEL[q.status] ?? q.status}
                        </span>
                      </div>
                    </li>
                  ))}
                </ul>
              </Section>
            )}

            {/* Pólizas */}
            {(full?.policies.length ?? 0) > 0 && (
              <Section
                icon="verified_user"
                title="Pólizas"
                badge={`${full!.policies.length}`}
              >
                <ul className="space-y-2">
                  {full!.policies.map((p) => (
                    <li
                      key={p.id}
                      className="flex items-center justify-between gap-2 rounded-lg border border-outline-variant/60 p-3 text-sm"
                    >
                      <div className="min-w-0">
                        <p className="font-mono text-xs font-bold text-on-surface">
                          {p.policyNumber}
                        </p>
                        <p className="text-[11px] text-outline">
                          {fmtDate(p.startDate)} → {fmtDate(p.endDate)}
                        </p>
                      </div>
                      <div className="shrink-0 text-right">
                        <p className="font-bold text-on-surface">
                          {formatCop(p.monthlyPremiumCop)}/mes
                        </p>
                        <span
                          className={`text-[10px] font-bold uppercase ${
                            p.status === 'VIGENTE' ? 'text-primary' : 'text-error'
                          }`}
                        >
                          {STATUS_LABEL[p.status] ?? p.status}
                        </span>
                      </div>
                    </li>
                  ))}
                </ul>
              </Section>
            )}

            {/* Reclamos */}
            {(full?.claims.length ?? 0) > 0 && (
              <Section
                icon="health_and_safety"
                title="Reclamos"
                badge={`${full!.claims.length}`}
              >
                <ul className="space-y-2">
                  {full!.claims.map((c) => {
                    const fraud = Number(c.fraudScore ?? 0)
                    return (
                      <li
                        key={c.id}
                        className="rounded-lg border border-outline-variant/60 p-3 text-sm"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <p className="font-mono text-xs font-bold">{c.claimNumber}</p>
                          <span className="text-[10px] font-bold text-primary uppercase">
                            {STATUS_LABEL[c.status] ?? c.status}
                          </span>
                        </div>
                        <p className="text-[11px] text-outline">
                          {c.insuranceType ?? ''}{' '}
                          {c.amountEstimateCop
                            ? `· Estimado ${formatCop(c.amountEstimateCop)}`
                            : ''}
                        </p>
                        {fraud >= 0.5 && (
                          <p className="mt-1 flex items-center gap-1 text-[11px] font-bold text-error">
                            <Icon name="report" filled className="text-[13px]" />
                            Posible fraude · score {fraud.toFixed(2)}
                          </p>
                        )}
                      </li>
                    )
                  })}
                </ul>
              </Section>
            )}

            {/* Documentos firmados / autorizaciones */}
            {customer && (
              <DocumentsSection
                documents={documents}
                consentData={customer.consentData}
                consentAt={customer.consentAt}
              />
            )}

            {/* Sesiones IA de voz con transcripción */}
            {(full?.aiCalls.length ?? 0) > 0 && (
              <Section
                icon="support_agent"
                title="Llamadas de voz con la IA"
                badge={`${full!.aiCalls.length}`}
              >
                <div className="space-y-2">
                  {full!.aiCalls.map((call) => (
                    <CallCard key={call.id} call={call} />
                  ))}
                </div>
              </Section>
            )}

            {/* Chat cliente↔IA (web/WhatsApp) — destino del botón "ver chat" */}
            {conversation.length > 0 && (
              <div id="chat-ia" className="scroll-mt-4">
                <ChatViewer turns={conversation} />
              </div>
            )}

            {/* Fallback demo: sin backend se mantiene el contenido mock */}
            {!full && !loading && (
              <>
                <section className="space-y-3">
                  <div className="flex items-center gap-2">
                    <div className="flex size-6 items-center justify-center rounded-full bg-primary-container text-on-primary-container">
                      <Icon name="smart_toy" className="text-sm" />
                    </div>
                    <h5 className="font-bold text-primary">Análisis de la IA</h5>
                  </div>
                  <div className="space-y-3 rounded-lg border border-primary/20 bg-primary-fixed/20 p-4">
                    <p className="text-sm leading-relaxed text-on-surface">
                      <span className="font-bold text-primary">
                        Siguiente Paso Sugerido:
                      </span>{' '}
                      {lead.insight}
                    </p>
                    <ul className="space-y-2">
                      {lead.checks.map((check) => (
                        <li key={check} className="flex items-start gap-2 text-xs">
                          <Icon
                            name="check_circle"
                            className="text-base text-primary"
                          />
                          <span>{check}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </section>
                {lead.transcript.length > 0 && (
                  <section className="space-y-4">
                    <h5 className="border-b border-outline-variant pb-2 font-bold text-on-surface">
                      Transcripción de la Llamada
                    </h5>
                    <div className="space-y-4 text-sm">
                      {lead.transcript.map((line) => (
                        <div
                          key={line.time + line.speaker}
                          className={`flex flex-col gap-1 ${line.side === 'client' ? 'items-end' : ''}`}
                        >
                          <span className="text-[10px] font-bold tracking-tighter text-outline uppercase">
                            {line.speaker} ({line.time})
                          </span>
                          <p
                            className={
                              line.side === 'bot'
                                ? 'mr-8 rounded-2xl rounded-tl-none bg-surface-container p-3'
                                : 'ml-8 rounded-2xl rounded-tr-none bg-primary p-3 text-on-primary'
                            }
                          >
                            {line.text}
                          </p>
                        </div>
                      ))}
                    </div>
                  </section>
                )}
              </>
            )}
          </div>
          <div className="border-t border-outline-variant bg-white p-5">
            <Button className="w-full rounded-2xl py-4">
              <Icon name="call" />
              Iniciar Llamada Ahora
            </Button>
          </div>
        </>
      ) : null}
    </aside>
    </>
  )
}
