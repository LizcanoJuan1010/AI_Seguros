import { Fragment } from 'react'
import { Icon } from '../../components/ui/Icon'
import { Button } from '../../components/ui/Button'
import type { AssistantPolicy, CheckoutStep } from './useAssistantChat'

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
        onClick={() =>
          window.open(policy.download_url, '_blank', 'noopener')
        }
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
