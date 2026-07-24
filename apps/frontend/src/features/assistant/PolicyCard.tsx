import { Fragment } from 'react'
import { Icon } from '../../components/ui/Icon'
import { Button } from '../../components/ui/Button'
import type {
  AssistantClaim,
  AssistantPayment,
  AssistantPolicy,
  AssistantUnderwriting,
  CheckoutStep,
} from './useAssistantChat'
import { downloadFile } from '../../lib/download'

/**
 * Piezas del CIERRE de la venta (reto Colsubsidio): el mini-stepper de progreso
 * que se alimenta del evento SSE `checkout_step`, y la tarjeta celebratoria de
 * póliza emitida que se alimenta del evento `policy`.
 *
 * Paleta Mist/Forest de Tequendama (tokens de src/index.css) — nada del
 * dark-azul de Paloma.
 */

const CHECKOUT_STEPS: ReadonlyArray<{
  key: CheckoutStep
  label: string
  icon: string
}> = [
  { key: 'datos', label: 'Datos', icon: 'badge' },
  { key: 'consentimiento', label: 'Consentimiento', icon: 'gavel' },
  { key: 'pago', label: 'Pago', icon: 'payments' },
  { key: 'emision', label: 'Emisión', icon: 'verified' },
]

/**
 * Mini-stepper horizontal Datos → Consentimiento → Pago → Emisión.
 * Discreto, bajo la respuesta del asistente. Marca el paso actual con
 * `bg-primary`/`text-primary`; los pendientes quedan en `text-on-surface-variant`.
 */
export function CheckoutStepper({ current }: { current: CheckoutStep }) {
  const currentIndex = CHECKOUT_STEPS.findIndex((s) => s.key === current)

  return (
    <div className="mt-3 rounded-xl border border-outline-variant/50 bg-surface-container-low/60 px-3 py-2.5">
      <p className="mb-2.5 flex items-center gap-1.5 text-label-sm font-semibold uppercase tracking-wide text-on-surface-variant">
        <Icon
          name="shopping_cart_checkout"
          className="text-[15px] text-primary"
        />
        Progreso del cierre
      </p>
      <ol className="flex items-start">
        {CHECKOUT_STEPS.map((step, i) => {
          const isDone = i < currentIndex
          const isActive = i === currentIndex
          const reached = isDone || isActive

          const circle = isActive
            ? 'bg-primary text-on-primary ring-4 ring-primary/15'
            : isDone
              ? 'bg-primary text-on-primary'
              : 'bg-surface-container-lowest border border-outline-variant text-on-surface-variant'

          return (
            <Fragment key={step.key}>
              <li className="flex min-w-0 flex-col items-center gap-1">
                <span
                  className={`flex size-7 items-center justify-center rounded-full transition-colors ${circle}`}
                >
                  <Icon
                    name={isDone ? 'check' : step.icon}
                    filled={isActive}
                    className="text-[16px]"
                  />
                </span>
                <span
                  className={`whitespace-nowrap text-label-sm leading-tight ${
                    reached
                      ? 'font-bold text-primary'
                      : 'font-semibold text-on-surface-variant'
                  }`}
                >
                  {step.label}
                </span>
              </li>
              {i < CHECKOUT_STEPS.length - 1 ? (
                <span
                  aria-hidden
                  className={`mt-[13px] h-0.5 flex-1 rounded-full ${
                    isDone ? 'bg-primary' : 'bg-outline-variant/60'
                  }`}
                />
              ) : null}
            </Fragment>
          )
        })}
      </ol>
    </div>
  )
}

const COP = new Intl.NumberFormat('es-CO', {
  style: 'currency',
  currency: 'COP',
  maximumFractionDigits: 0,
})

/** Estado del pago → chip (label, icono y tono). */
const PAYMENT_BADGE: Record<
  AssistantPayment['status'],
  { label: string; icon: string; className: string }
> = {
  PENDING: {
    label: 'Pendiente de pago',
    icon: 'schedule',
    className: 'border-amber-cta/50 bg-amber-cta/15 text-on-secondary-fixed-variant',
  },
  APPROVED: {
    label: 'Pago aprobado',
    icon: 'check_circle',
    className: 'border-primary/25 bg-primary-fixed text-primary',
  },
  DECLINED: {
    label: 'Pago rechazado',
    icon: 'cancel',
    className: 'border-error/40 bg-error-container/50 text-on-error-container',
  },
  VOIDED: {
    label: 'Pago anulado',
    icon: 'undo',
    className: 'border-outline-variant bg-surface-container-low text-on-surface-variant',
  },
  ERROR: {
    label: 'Error en la pasarela',
    icon: 'error',
    className: 'border-error/40 bg-error-container/50 text-on-error-container',
  },
  REFUND_REQUESTED: {
    label: 'En aclaración / reembolso',
    icon: 'currency_exchange',
    className: 'border-amber-cta/50 bg-amber-cta/15 text-on-secondary-fixed-variant',
  },
}

/**
 * Tarjeta del pago real (evento SSE `payment_link`): monto, estado y CTA al
 * checkout seguro de Polar. La tarjeta débito/crédito se digita SOLO en la
 * página de la pasarela — el chat nunca pide datos de tarjeta.
 */
export function PaymentCard({ payment }: { payment: AssistantPayment }) {
  const badge = PAYMENT_BADGE[payment.status] ?? PAYMENT_BADGE.PENDING
  const payable = payment.status === 'PENDING' && !!payment.checkout_url

  return (
    <div className="mt-3 overflow-hidden rounded-xl border border-outline-variant/50 bg-surface-container-low/60">
      <div className="flex items-center justify-between gap-2 px-4 pt-3">
        <p className="flex items-center gap-1.5 text-label-sm font-semibold uppercase tracking-wide text-on-surface-variant">
          <Icon name="credit_card" className="text-[15px] text-primary" />
          Pago seguro{payment.demo ? ' · demo' : ' · Polar'}
        </p>
        <span
          className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-label-sm font-semibold ${badge.className}`}
        >
          <Icon name={badge.icon} filled className="text-[14px]" />
          {badge.label}
        </span>
      </div>

      <div className="px-4 py-3">
        {typeof payment.amount_cop === 'number' ? (
          <p className="text-headline-md font-bold text-on-surface">
            {COP.format(payment.amount_cop)}
            <span className="ml-1 align-middle text-label-sm font-semibold text-on-surface-variant">
              COP
            </span>
          </p>
        ) : null}
        {payment.concept ? (
          <p className="mt-0.5 text-body-md text-on-surface-variant">
            {payment.concept}
          </p>
        ) : null}
        <p className="mt-1 font-mono text-label-sm text-outline">
          Ref. {payment.reference}
        </p>

        {payable ? (
          <Button
            variant="cta"
            className="mt-3 w-full rounded-full"
            onClick={() =>
              window.open(payment.checkout_url as string, '_blank', 'noopener')
            }
          >
            <Icon name="lock" filled className="text-[18px]" />
            Pagar con tarjeta débito o crédito
          </Button>
        ) : null}

        {payment.status === 'PENDING' && !payment.checkout_url ? (
          <p className="mt-2 flex items-center gap-1.5 text-label-sm text-on-surface-variant">
            <Icon name="science" className="text-[15px] text-outline" />
            Pasarela en modo demo: el pago se simula al confirmar en el chat.
          </p>
        ) : null}
      </div>

      <p className="flex items-center gap-1.5 border-t border-outline-variant/40 px-4 py-2 text-label-sm text-on-surface-variant">
        <Icon name="verified_user" filled className="text-[14px] text-primary" />
        Tus datos de tarjeta se digitan solo en la página segura de la pasarela.
      </p>
    </div>
  )
}

/**
 * Tarjeta celebratoria de póliza emitida — el momento "ya quedé asegurada".
 * Verde bosque (`bg-primary`/`text-on-primary`), check grande en disco ámbar,
 * número de póliza en grande (`text-headline-md font-mono`) y CTA ámbar de
 * descarga que abre el PDF.
 */
export function PolicyCard({ policy }: { policy: AssistantPolicy }) {
  return (
    <div className="ai-glow soft-forest-shadow relative overflow-hidden rounded-2xl bg-primary p-5 text-on-primary">
      {/* Halo decorativo, sutil y corporativo */}
      <div
        aria-hidden
        className="pointer-events-none absolute -right-8 -top-10 size-32 rounded-full bg-amber-cta/10 blur-2xl"
      />

      <div className="relative flex items-center gap-3">
        <div className="flex size-14 flex-shrink-0 items-center justify-center rounded-full bg-amber-cta text-primary shadow-md shadow-amber-cta/25">
          <Icon name="verified" filled className="text-[34px]" />
        </div>
        <div className="min-w-0">
          <p className="text-label-sm uppercase tracking-wide text-primary-fixed-dim">
            {policy.title}
          </p>
          <h3 className="text-headline-md font-bold leading-tight text-on-primary">
            ¡Ya quedaste asegurada!
          </h3>
        </div>
      </div>

      <div className="relative mt-4 rounded-xl border border-on-primary/15 bg-on-primary/10 px-4 py-3">
        <p className="text-label-sm uppercase tracking-wide text-primary-fixed-dim">
          Número de póliza
        </p>
        <p className="mt-0.5 text-headline-md font-mono font-bold tracking-wide text-on-primary">
          {policy.policyNumber}
        </p>
      </div>

      <Button
        variant="cta"
        className="relative mt-4 w-full rounded-full"
        onClick={() => downloadFile(policy.download_url)}
      >
        <Icon name="download" filled className="text-[18px]" />
        Descargar póliza (PDF)
      </Button>

      <p className="relative mt-2.5 flex items-center justify-center gap-1 text-label-sm text-primary-fixed-dim">
        <Icon name="shield" filled className="text-[14px]" />
        Cobertura vigente · Colsubsidio distribuye
      </p>
    </div>
  )
}

/** Estado del reclamo → chip (label, icono y tono). */
const CLAIM_BADGE: Record<
  string,
  { label: string; icon: string; className: string }
> = {
  REPORTADO: {
    label: 'Reportado',
    icon: 'assignment_turned_in',
    className: 'border-primary/25 bg-primary-fixed text-primary',
  },
  EN_REVISION: {
    label: 'En revisión',
    icon: 'schedule',
    className: 'border-amber-cta/50 bg-amber-cta/15 text-on-secondary-fixed-variant',
  },
  DOCS_PENDIENTES: {
    label: 'Documentos pendientes',
    icon: 'upload_file',
    className: 'border-amber-cta/50 bg-amber-cta/15 text-on-secondary-fixed-variant',
  },
  APROBADO: {
    label: 'Aprobado',
    icon: 'check_circle',
    className: 'border-primary/25 bg-primary-fixed text-primary',
  },
  PAGADO: {
    label: 'Pagado',
    icon: 'payments',
    className: 'border-primary/25 bg-primary-fixed text-primary',
  },
  RECHAZADO: {
    label: 'Rechazado',
    icon: 'cancel',
    className: 'border-error/40 bg-error-container/50 text-on-error-container',
  },
}

/**
 * Tarjeta del reclamo/siniestro (evento SSE `claim`): número CLM-..., estado y
 * documentos de soporte que el cliente puede subir por el mismo chat.
 */
export function ClaimCard({ claim }: { claim: AssistantClaim }) {
  const badge = CLAIM_BADGE[claim.status] ?? CLAIM_BADGE.REPORTADO
  const docs = claim.documentos_requeridos ?? []

  return (
    <div className="mt-3 overflow-hidden rounded-xl border border-outline-variant/50 bg-surface-container-low/60">
      <div className="flex items-center justify-between gap-2 px-4 pt-3">
        <p className="flex items-center gap-1.5 text-label-sm font-semibold uppercase tracking-wide text-on-surface-variant">
          <Icon name="health_and_safety" className="text-[15px] text-primary" />
          {claim.title}
        </p>
        <span
          className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-label-sm font-semibold ${badge.className}`}
        >
          <Icon name={badge.icon} filled className="text-[14px]" />
          {badge.label}
        </span>
      </div>

      <div className="px-4 py-3">
        <p className="text-label-sm uppercase tracking-wide text-on-surface-variant">
          Número de reclamo
        </p>
        <p className="mt-0.5 text-headline-md font-mono font-bold tracking-wide text-on-surface">
          {claim.claimNumber}
        </p>
        {claim.poliza ? (
          <p className="mt-1 text-label-sm text-outline">
            Póliza {claim.poliza}
            {claim.tipo ? ` · ${claim.tipo}` : ''}
          </p>
        ) : null}

        {docs.length > 0 ? (
          <div className="mt-3 rounded-lg border border-outline-variant/40 bg-surface-container-lowest px-3 py-2">
            <p className="mb-1 text-label-sm font-semibold text-on-surface-variant">
              Documentos de soporte (puedes enviarlos por este chat):
            </p>
            <ul className="space-y-0.5">
              {docs.map((d) => (
                <li
                  key={d}
                  className="flex items-start gap-1.5 text-label-sm text-on-surface-variant"
                >
                  <Icon
                    name="attach_file"
                    className="mt-px text-[13px] text-primary"
                  />
                  {d}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>

      <p className="flex items-center gap-1.5 border-t border-outline-variant/40 px-4 py-2 text-label-sm text-on-surface-variant">
        <Icon name="notifications_active" filled className="text-[14px] text-primary" />
        Te avisaremos aquí con cada cambio de estado.
      </p>
    </div>
  )
}

/** Decisión de underwriting → presentación de la tarjeta. */
const UW_STYLE: Record<
  AssistantUnderwriting['decision'],
  { icon: string; title: string; className: string; iconClass: string }
> = {
  AUTO_APPROVE: {
    icon: 'task_alt',
    title: 'Aprobación automática',
    className: 'border-primary/25 bg-primary-fixed/60',
    iconClass: 'bg-primary text-on-primary',
  },
  REFER: {
    icon: 'supervisor_account',
    title: 'Un asesor revisa tu caso',
    className: 'border-amber-cta/50 bg-amber-cta/10',
    iconClass: 'bg-amber-cta text-primary',
  },
  DECLINE: {
    icon: 'block',
    title: 'No pudimos emitir por este canal',
    className: 'border-error/40 bg-error-container/40',
    iconClass: 'bg-error text-on-error',
  },
}

/**
 * Tarjeta de la decisión de underwriting (evento SSE `underwriting`):
 * verde si la emisión es automática, ámbar si escala a un gerente (con la
 * promesa de respuesta <24h), roja si no es asegurable por este canal.
 */
export function UnderwritingCard({
  underwriting,
}: {
  underwriting: AssistantUnderwriting
}) {
  const style = UW_STYLE[underwriting.decision] ?? UW_STYLE.REFER

  return (
    <div
      className={`mt-3 overflow-hidden rounded-xl border px-4 py-3 ${style.className}`}
    >
      <div className="flex items-center gap-2.5">
        <span
          className={`flex size-8 flex-shrink-0 items-center justify-center rounded-full ${style.iconClass}`}
        >
          <Icon name={style.icon} filled className="text-[18px]" />
        </span>
        <div className="min-w-0">
          <p className="text-label-sm uppercase tracking-wide text-on-surface-variant">
            Evaluación de riesgo
          </p>
          <p className="font-bold leading-tight text-on-surface">{style.title}</p>
        </div>
      </div>
      {underwriting.decision !== 'AUTO_APPROVE' &&
      underwriting.reasons.length > 0 ? (
        <ul className="mt-2 space-y-0.5">
          {underwriting.reasons.map((r) => (
            <li
              key={r}
              className="flex items-start gap-1.5 text-label-sm text-on-surface-variant"
            >
              <Icon name="info" className="mt-px text-[13px] text-primary" />
              {r}
            </li>
          ))}
        </ul>
      ) : null}
      {underwriting.decision === 'REFER' ? (
        <p className="mt-2 text-label-sm text-on-surface-variant">
          Te confirmamos en menos de 24 horas — tu solicitud ya está en el panel
          del equipo.
        </p>
      ) : null}
    </div>
  )
}
