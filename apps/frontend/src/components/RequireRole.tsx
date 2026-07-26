/**
 * Guarda de ROL: se anida DENTRO de un árbol ya envuelto por `RequireAuth`
 * (ver App.tsx) — no repite el manejo de `status`/spinner/login, solo exige
 * que `user.role` esté en `roles`. Sin coincidencia, redirige a /asistente
 * en vez de mostrar la sección (no hay pantalla de "403" propia todavía).
 */
import type { ReactNode } from 'react'
import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'

export function RequireRole({ roles, children }: { roles: string[]; children?: ReactNode }) {
  const { user } = useAuth()
  const allowed = roles.map((r) => r.toUpperCase())

  if (!user || !allowed.includes(user.role.toUpperCase())) {
    return <Navigate to="/asistente" replace />
  }

  return <>{children ?? <Outlet />}</>
}
