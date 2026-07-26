import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { ChecklistSteps, type ChecklistStepItem } from '../components/ChecklistSteps'
import { Icon } from '../components/ui/Icon'

/**
 * Checklist de activación: página pública (sin login), el link que Mónica/
 * Sofía le mandan al cliente por WhatsApp/correo (`generar_checklist_activacion`).
 * No vence — el cliente la retoma cuando quiera. GET pinta el estado guardado
 * de inmediato; el POST /refrescar (solo lo dispara un navegador real
 * ejecutando este componente, nunca un escáner de link de correo) revisa si
 * ya se puede avanzar al siguiente paso.
 */

type Ficha = {
  pdf_url?: string | null
  producto?: string | null
  aseguradora?: string | null
  coberturas?: string[]
}

type EstadoChecklist = {
  paso_actual: string
  pasos: ChecklistStepItem[]
  nombre_cliente?: string | null
  ficha?: Ficha | null
}

type Phase = 'loading' | 'ready' | 'notfound' | 'error'

// El paso "link" siempre viene "completado" desde el backend (si estás viendo
// esta página, el link ya existe) — no se muestra como checkbox, es implícito.
const LABELS: Record<string, string> = {
  cedula: 'Cédula (verificación de identidad)',
  reconocimiento_facial: 'Reconocimiento facial',
  firma: 'Firma de la póliza',
  pago: 'Pago de la prima',
}

const MENSAJE_POR_PASO: Record<string, string> = {
  en_revision: 'Tu solicitud está en revisión de un asesor. Te confirmamos en menos de 24 horas.',
  rechazado: 'No fue posible continuar por este canal. Un asesor se pondrá en contacto contigo.',
  completado: '¡Ya completaste todo! Estamos terminando de emitir tu póliza.',
}

export function ChecklistPage() {
  const { token } = useParams<{ token: string }>()
  const [phase, setPhase] = useState<Phase>('loading')
  const [estado, setEstado] = useState<EstadoChecklist | null>(null)

  useEffect(() => {
    if (!token) return
    let alive = true

    const cargar = async () => {
      try {
        const r = await fetch(`/api/checklist/${token}`)
        if (r.status === 404) {
          if (alive) setPhase('notfound')
          return
        }
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        const inicial = (await r.json()) as EstadoChecklist
        if (!alive) return
        setEstado(inicial)
        setPhase('ready')

        const r2 = await fetch(`/api/checklist/${token}/refrescar`, { method: 'POST' })
        if (r2.ok) {
          const fresco = (await r2.json()) as EstadoChecklist
          if (alive) setEstado((prev) => ({ ...fresco, nombre_cliente: prev?.nombre_cliente }))
        }
      } catch {
        if (alive) setPhase('error')
      }
    }
    cargar()
    return () => {
      alive = false
    }
  }, [token])

  const pasosConLabel =
    estado?.pasos
      .filter((p) => p.id !== 'link')
      .map((p) => ({ ...p, label: LABELS[p.id] ?? p.id })) ?? []
  const pasoActivo = estado?.pasos.find((p) => p.estado === 'actual')
  const mensajeEspecial = estado ? MENSAJE_POR_PASO[estado.paso_actual] : null

  return (
    <div className="flex min-h-svh items-center justify-center bg-background p-4">
      <div className="w-full max-w-md">
        <div className="mb-4 flex items-center gap-2">
          <Icon name="shield" filled className="text-2xl text-primary" />
          <p className="text-lg font-bold text-on-surface">Activa tu póliza</p>
        </div>

        {phase === 'loading' ? (
          <p className="text-sm text-on-surface-variant">Cargando tu checklist…</p>
        ) : null}

        {phase === 'notfound' ? (
          <p className="flex items-center gap-2 text-sm text-on-error-container">
            <Icon name="error" filled className="text-error" />
            No encontramos este link. Pídele a tu asesor que te lo reenvíe.
          </p>
        ) : null}

        {phase === 'error' ? (
          <p className="flex items-center gap-2 text-sm text-on-error-container">
            <Icon name="error" filled className="text-error" />
            No pudimos cargar tu checklist en este momento. Intenta de nuevo en un momento.
          </p>
        ) : null}

        {phase === 'ready' && estado ? (
          <>
            {estado.nombre_cliente ? (
              <p className="mb-3 text-sm text-on-surface-variant">Hola, {estado.nombre_cliente}</p>
            ) : null}

            {estado.ficha?.pdf_url ? (
              <a
                href={estado.ficha.pdf_url}
                target="_blank"
                rel="noreferrer"
                className="mb-4 flex items-center gap-2 rounded-lg bg-surface-variant p-3 text-sm font-bold text-on-surface"
              >
                <Icon name="picture_as_pdf" filled className="text-[18px] text-primary" />
                Ver la ficha de tu seguro{estado.ficha.producto ? ` — ${estado.ficha.producto}` : ''}
              </a>
            ) : null}

            <ChecklistSteps pasos={pasosConLabel} />

            {mensajeEspecial ? (
              <p className="mt-4 rounded-lg bg-surface-variant p-3 text-sm text-on-surface">
                {mensajeEspecial}
              </p>
            ) : pasoActivo?.url ? (
              <a
                href={pasoActivo.url}
                className="mt-4 flex items-center justify-center gap-2 rounded-full bg-primary px-4 py-3 text-sm font-bold text-on-primary"
              >
                <Icon name="arrow_forward" filled className="text-[18px]" />
                Continuar
              </a>
            ) : pasoActivo ? (
              <p className="mt-4 rounded-lg bg-surface-variant p-3 text-sm text-on-surface">
                Ya te enviamos este paso por WhatsApp o correo — revisa tu bandeja para continuar.
              </p>
            ) : null}
          </>
        ) : null}
      </div>
    </div>
  )
}
