import { Outlet } from 'react-router-dom'
import { TopNav } from '../components/chrome/TopNav'

/**
 * Alto fijo (como AppShellLayout) pero con el nav público (como
 * MarketingLayout): lo usa /asistente, que debe verse sin login para
 * visitantes anónimos y sin la barra interna de Vendedor/Gerente/Campañas.
 */
export function ChatShellLayout() {
  return (
    <div className="flex h-svh flex-col bg-mist-white text-on-surface">
      <TopNav variant="marketing" />
      <div className="min-h-0 w-full flex-1 overflow-auto">
        <Outlet />
      </div>
    </div>
  )
}
