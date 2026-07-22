/**
 * Helper de autenticación para llamadas fuera del árbol de React (chat SSE,
 * fetch manual). Lee el access token de localStorage — misma clave que persiste
 * el AuthContext (`teq_access_token`) — y devuelve el header `Authorization`.
 *
 * El tenant (equipo) ya NO se envía como header: viaja dentro del JWT y el
 * backend/IA lo extrae de los claims. Por eso basta con el Bearer.
 */

const LS_ACCESS = 'teq_access_token'

/** Lee el access token persistido, o null si no hay sesión. */
export function getAccessToken(): string | null {
  try {
    return localStorage.getItem(LS_ACCESS)
  } catch {
    return null
  }
}

/**
 * Devuelve `{ Authorization: 'Bearer <token>' }` si hay sesión, u objeto vacío
 * si no la hay (para no mandar un header "Bearer null" en peticiones públicas).
 */
export function authHeaders(): Record<string, string> {
  const token = getAccessToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}
