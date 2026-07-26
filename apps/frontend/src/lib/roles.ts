/**
 * Roles del personal (staff). El login existe SOLO para gerentes, admins y
 * agentes; el cliente final nunca tiene usuario: entra directo al chat con
 * identidad de dispositivo (ver lib/clientIdentity.ts).
 */

/** true si el rol corresponde a personal interno (puede ver el panel). */
export function isStaff(role: string | undefined | null): boolean {
  const r = (role ?? '').toUpperCase()
  return r === 'GERENTE' || r === 'ADMIN' || r === 'AGENTE'
}

/** true si el rol es de gerencia (GERENTE/ADMIN). */
export function isManager(role: string | undefined | null): boolean {
  const r = (role ?? '').toUpperCase()
  return r === 'GERENTE' || r === 'ADMIN'
}

/**
 * Ruta "home" según rol. Todo el staff aterriza en el panel: la gerencia en el
 * Resumen y los agentes directo en la pestaña Clientes (donde vive el
 * expediente 360 que antes era la bandeja del vendedor).
 */
export function homeForRole(role: string | undefined | null): string {
  if (isManager(role)) return '/gerente'
  if (isStaff(role)) return '/gerente?tab=clientes'
  return '/asistente'
}
