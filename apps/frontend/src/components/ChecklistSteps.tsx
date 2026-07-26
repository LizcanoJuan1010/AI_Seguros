import { Card } from './ui/Card'
import { Chip } from './ui/Chip'
import { Icon } from './ui/Icon'

export type ChecklistStepStatus = 'completado' | 'actual' | 'bloqueado'

export type ChecklistStepItem = {
  id: string
  label: string
  estado: ChecklistStepStatus
  url?: string | null
}

const toneByStatus: Record<ChecklistStepStatus, 'success' | 'hot' | 'neutral'> = {
  completado: 'success',
  actual: 'hot',
  bloqueado: 'neutral',
}

const labelByStatus: Record<ChecklistStepStatus, string> = {
  completado: 'Completado',
  actual: 'En curso',
  bloqueado: 'Pendiente',
}

const iconByStatus: Record<ChecklistStepStatus, string> = {
  completado: 'check_circle',
  actual: 'radio_button_checked',
  bloqueado: 'lock',
}

/**
 * Tracker de pasos reutilizable — se arma con los primitivos ya existentes
 * (Card + Chip + Icon), no depende de esta página en particular.
 */
export function ChecklistSteps({ pasos }: { pasos: ChecklistStepItem[] }) {
  return (
    <div className="flex flex-col gap-3">
      {pasos.map((paso, i) => (
        <Card key={paso.id} className="flex items-center gap-3 p-4">
          <Icon
            name={iconByStatus[paso.estado]}
            filled
            className={`text-[22px] ${
              paso.estado === 'completado'
                ? 'text-primary'
                : paso.estado === 'actual'
                  ? 'text-amber-cta'
                  : 'text-outline'
            }`}
          />
          <div className="flex-1">
            <p className="text-xs uppercase tracking-wide text-on-surface-variant">
              Paso {i + 1}
            </p>
            <p className="text-sm font-bold text-on-surface">{paso.label}</p>
          </div>
          <Chip tone={toneByStatus[paso.estado]}>{labelByStatus[paso.estado]}</Chip>
        </Card>
      ))}
    </div>
  )
}
