/**
 * Guarda de rutas: protege el árbol que envuelve.
 *
 *  - `status === 'loading'`  → spinner (mientras se restaura la sesión).
 *  - `unauthenticated`       → redirige a `/login`.
 *  - `authenticated`         → renderiza `children` (o `<Outlet />` si se usa
 *                              como layout route sin hijos explícitos).
 */
import type { ReactNode } from 'react'
import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'

function Spinner() {
  return (
    <div className="flex h-svh w-full items-center justify-center bg-mist-white">
      <div
        className="size-10 animate-spin rounded-full border-4 border-outline-variant border-t-primary"
        role="status"
        aria-label="Cargando"
      />
    </div>
  )
}

export function RequireAuth({ children }: { children?: ReactNode }) {
  const { status } = useAuth()

  if (status === 'loading') return <Spinner />
  if (status === 'unauthenticated') return <Navigate to="/login" replace />

  return <>{children ?? <Outlet />}</>
}
