/**
 * Contexto de autenticación del frontend (adaptado del AuthContext de Paloma).
 *
 * Diferencias con Paloma:
 *  - Aquí es React Router 7 + Vite (no Next.js): sin `"use client"`, sin cookies
 *    de servidor, sin `getApiBase`. Se usan rutas relativas `/api/...` que el
 *    proxy de Vite (dev) o nginx (prod) reenvía al backend.
 *  - El JWT lleva `teamId` (el tenant) y `role`: ambos se leen decodificando el
 *    payload del access token en el cliente (sin verificar firma).
 *
 * Persiste en localStorage con claves `teq_*`. Auto-refresca el access token
 * 2 minutos antes de expirar usando el refresh token.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

// ---------------------------------------------------------------------------
// Tipos
// ---------------------------------------------------------------------------

export interface AuthUser {
  id: string
  email: string
  name: string
  role: string
  /** Tenant (equipo) al que pertenece el usuario; viaja dentro del JWT. */
  teamId: string
}

export type AuthStatus = 'loading' | 'authenticated' | 'unauthenticated'

interface AuthContextValue {
  user: AuthUser | null
  status: AuthStatus
  /** Inicia sesión contra `POST /api/v1/auth/login`. */
  signIn: (email: string, password: string) => Promise<{ ok: boolean; error?: string }>
  /** Cierra sesión: limpia el estado y el almacenamiento local. */
  signOut: () => void
  /** Access token crudo (para SSE / fetch manual vía authHeaders). */
  accessToken: string | null
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  status: 'loading',
  signIn: async () => ({ ok: false }),
  signOut: () => {},
  accessToken: null,
})

// ---------------------------------------------------------------------------
// Endpoints y claves de almacenamiento
// ---------------------------------------------------------------------------

const LOGIN_ENDPOINT = 'http://localhost:3000/api/v1/auth/login'
const REFRESH_ENDPOINT = 'http://localhost:3000/api/v1/auth/refresh'

const LS_ACCESS = 'teq_access_token'
const LS_REFRESH = 'teq_refresh_token'
const LS_USER = 'teq_user'

function lsGet(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}
function lsSet(key: string, value: string) {
  try {
    localStorage.setItem(key, value)
  } catch {
    /* almacenamiento no disponible */
  }
}
function lsRemove(key: string) {
  try {
    localStorage.removeItem(key)
  } catch {
    /* almacenamiento no disponible */
  }
}

// ---------------------------------------------------------------------------
// Helpers de JWT (decode en cliente — sin verificar firma, solo lee el payload)
// ---------------------------------------------------------------------------

type JwtPayload = {
  sub?: string
  email?: string
  name?: string
  role?: string
  teamId?: string
  exp?: number
  [k: string]: unknown
}

function decodePayload(token: string): JwtPayload | null {
  try {
    const parts = token.split('.')
    if (parts.length !== 3) return null
    const json = atob(parts[1].replace(/-/g, '+').replace(/_/g, '/'))
    return JSON.parse(json) as JwtPayload
  } catch {
    return null
  }
}

function isTokenExpired(token: string): boolean {
  const p = decodePayload(token)
  if (!p || typeof p.exp !== 'number') return true
  return p.exp * 1000 < Date.now()
}

/** Tipo laxo de lo que devuelve el backend en `user`. */
type RawUser = {
  id?: string
  email?: string
  name?: string
  role?: string
  teamId?: string | null
}

/**
 * Construye el AuthUser combinando el objeto `user` de la respuesta con los
 * claims del access token. El token es la fuente de verdad para `role`/`teamId`
 * (el tenant sale del login), por eso se prefiere lo que trae el JWT.
 */
function buildUser(raw: RawUser | undefined, accessToken: string): AuthUser {
  const claims = decodePayload(accessToken) ?? {}
  return {
    id: raw?.id ?? claims.sub ?? '',
    email: raw?.email ?? claims.email ?? '',
    name: raw?.name ?? claims.name ?? raw?.email ?? claims.email ?? '',
    role: claims.role ?? raw?.role ?? '',
    teamId: claims.teamId ?? raw?.teamId ?? '',
  }
}

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [status, setStatus] = useState<AuthStatus>('loading')
  const [accessToken, setAccessToken] = useState<string | null>(null)

  // ---- Limpia todo el estado de sesión ----
  const clearAuth = useCallback(() => {
    setUser(null)
    setAccessToken(null)
    setStatus('unauthenticated')
    lsRemove(LS_ACCESS)
    lsRemove(LS_REFRESH)
    lsRemove(LS_USER)
  }, [])

  // ---- Persiste el estado de sesión ----
  const persistAuth = useCallback((u: AuthUser, at: string, rt: string) => {
    setUser(u)
    setAccessToken(at)
    setStatus('authenticated')
    lsSet(LS_ACCESS, at)
    lsSet(LS_REFRESH, rt)
    lsSet(LS_USER, JSON.stringify(u))
  }, [])

  // ---- Refresca el access token con el refresh token ----
  const refresh = useCallback(async (): Promise<boolean> => {
    const rt = lsGet(LS_REFRESH)
    if (!rt || isTokenExpired(rt)) return false
    try {
      const res = await fetch(REFRESH_ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: rt }),
      })
      if (!res.ok) return false
      const data = (await res.json()) as { access_token: string; user?: RawUser }
      const u = buildUser(data.user, data.access_token)
      // El refresh conserva el mismo refresh token (solo rota el access).
      persistAuth(u, data.access_token, rt)
      return true
    } catch {
      return false
    }
  }, [persistAuth])

  // ---- Boot: restaura la sesión desde localStorage ----
  useEffect(() => {
    ;(async () => {
      const at = lsGet(LS_ACCESS)
      const rt = lsGet(LS_REFRESH)
      const storedUser = lsGet(LS_USER)

      if (!at || !rt) {
        clearAuth()
        return
      }

      // Si el access token sigue vigente, úsalo tal cual.
      if (!isTokenExpired(at) && storedUser) {
        try {
          const u = JSON.parse(storedUser) as AuthUser
          setUser(u)
          setAccessToken(at)
          setStatus('authenticated')
          return
        } catch {
          /* cae al refresh */
        }
      }

      // Si el access expiró (o falta el user), intenta refrescar.
      const ok = await refresh()
      if (!ok) clearAuth()
    })()
  }, [clearAuth, refresh])

  // ---- Auto-refresh 2 minutos antes de expirar ----
  useEffect(() => {
    if (!accessToken) return
    const payload = decodePayload(accessToken)
    if (!payload || typeof payload.exp !== 'number') return

    const msUntilExpiry = payload.exp * 1000 - Date.now()
    // Refresca 2 minutos antes de expirar (mínimo 10s para evitar bucles).
    const msUntilRefresh = Math.max(msUntilExpiry - 120_000, 10_000)

    const timer = window.setTimeout(() => {
      void refresh()
    }, msUntilRefresh)

    return () => window.clearTimeout(timer)
  }, [accessToken, refresh])

  // ---- signIn ----
  const signIn = useCallback(
    async (email: string, password: string): Promise<{ ok: boolean; error?: string }> => {
      try {
        const res = await fetch(LOGIN_ENDPOINT, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password }),
        })
        if (!res.ok) {
          const body = (await res.json().catch(() => ({}))) as {
            message?: string | string[]
            detail?: string
          }
          const msg = Array.isArray(body.message)
            ? body.message.join(', ')
            : body.message || body.detail
          return { ok: false, error: msg || 'Credenciales inválidas' }
        }
        const data = (await res.json()) as {
          access_token: string
          refresh_token: string
          user?: RawUser
        }
        const u = buildUser(data.user, data.access_token)
        persistAuth(u, data.access_token, data.refresh_token)
        return { ok: true }
      } catch {
        return { ok: false, error: 'Error de conexión con el servidor' }
      }
    },
    [persistAuth],
  )

  // ---- signOut ----
  const signOut = useCallback(() => {
    clearAuth()
  }, [clearAuth])

  const value = useMemo<AuthContextValue>(
    () => ({ user, status, signIn, signOut, accessToken }),
    [user, status, signIn, signOut, accessToken],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useAuth() {
  return useContext(AuthContext)
}
