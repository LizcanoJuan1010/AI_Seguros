/**
 * Envoltorio reusable del expediente 360° (LeadDetailDrawer) para abrirlo con
 * solo un `customerId`, desde donde no hay un objeto Lead completo: la Cartera
 * de Clientes y los Reclamos del panel del gerente. Construye un Lead mínimo
 * (el drawer carga TODO por customerId vía GET /customers/:id/full).
 */
import type { Lead } from '../../data/mock/types'
import { LeadDetailDrawer } from './LeadDetailDrawer'

type Props = {
  customerId: string | null
  name?: string | null
  /** Tono/etiqueta de intención para el chip; opcional. */
  intent?: 'hot' | 'warm' | 'cold'
  intentLabel?: string
  /** Lead concreto a resaltar; si se omite, el drawer toma el más relevante. */
  leadId?: string
  open: boolean
  onClose: () => void
}

function initialsOf(name: string): string {
  return (
    name
      .split(' ')
      .slice(0, 2)
      .map((w) => w[0] ?? '')
      .join('')
      .toUpperCase() || '?'
  )
}

export function CustomerDetailDrawer({
  customerId,
  name,
  intent,
  intentLabel,
  leadId,
  open,
  onClose,
}: Props) {
  const displayName = name || 'Cliente'
  const lead: Lead | null = customerId
    ? {
        id: leadId ?? '',
        customerId,
        name: displayName,
        initials: initialsOf(displayName),
        when: '',
        type: '',
        typeIcon: 'shield',
        summary: '',
        intent: intent ?? 'warm',
        intentLabel: intentLabel ?? '',
        premium: '—',
        phone: '—',
        email: '—',
        location: 'Colombia',
        status: 'seguimiento',
        insight: '',
        checks: [],
        transcript: [],
      }
    : null

  return <LeadDetailDrawer lead={lead} open={open} onClose={onClose} />
}
