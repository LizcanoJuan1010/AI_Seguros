/**
 * Guarda de rutas: protege el árbol que envuelve SIN sacar al usuario.
 *
 *  - `status === 'loading'`  → spinner (mientras se restaura la sesión).
 *  - `unauthenticated`       → mantiene la RUTA actual y muestra el login
 *                              como pop-up encima (LoginModal); al ingresar,
 *                              la vista continúa donde estaba.
 *  - `authenticated`         → renderiza `children` (o `<Outlet />` si se usa
 *                              como layout route sin hijos explícitos).
 */
import type { ReactNode } from 'react'
import { Outlet } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import { LoginModal } from './LoginModal'
import { MistBackground } from '../features/landing/MistBackground'

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
  if (status === 'unauthenticated') {
    // Sin sesión: no se navega a /login ni se pierde la URL — el fondo Mist
    // ocupa la vista y el modal pide credenciales encima.
    return (
      <div className="relative min-h-svh">
        <MistBackground />
        <LoginModal />
      </div>
    )
  }

  return <>{children ?? <Outlet />}</>
}
