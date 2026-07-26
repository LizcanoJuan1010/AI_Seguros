/**
 * Identidad anónima del cliente final ("cuenta" sin registro).
 *
 * El cliente NO hace login: en su primera visita se genera un `device_id`
 * (UUID) que persiste en localStorage y viaja en cada turno del chat. El
 * servicio IA lo usa como user_id (`web:<device_id>`), así la memoria, los
 * leads y las cotizaciones sobreviven entre conversaciones y visitas.
 *
 * A diferencia del session_id (una conversación, rotable), el device_id es
 * durable: es lo más parecido a una cuenta que tiene el cliente hasta que
 * entrega un dato real (teléfono) dentro del flujo.
 */

const LS_DEVICE = 'teq_device_id'

/** Cache en memoria: mantiene el id estable dentro de la pestaña aunque
 *  localStorage no esté disponible (modo incógnito restrictivo, iframes). */
let inMemoryId: string | null = null

function freshId(): string {
  const rnd =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`
  return `dev_${rnd}`
}

/** Devuelve el device_id del navegador, creándolo en la primera visita. */
export function getDeviceId(): string {
  if (inMemoryId) return inMemoryId
  try {
    const existing = window.localStorage.getItem(LS_DEVICE)
    if (existing) {
      inMemoryId = existing
      return existing
    }
    const id = freshId()
    window.localStorage.setItem(LS_DEVICE, id)
    inMemoryId = id
    return id
  } catch {
    inMemoryId = freshId()
    return inMemoryId
  }
}
