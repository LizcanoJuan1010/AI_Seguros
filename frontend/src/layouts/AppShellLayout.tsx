import { Outlet, useLocation } from 'react-router-dom'
import { SidebarNav } from '../components/chrome/SidebarNav'
import { TopNav } from '../components/chrome/TopNav'

export function AppShellLayout() {
  const { pathname } = useLocation()
  const role = pathname.startsWith('/gerente') ? 'manager' : 'agent'

  return (
    <div className="flex min-h-svh flex-col bg-mist-white text-on-surface">
      <TopNav variant="app" />
      <div className="flex min-h-0 flex-1 overflow-hidden">
        <SidebarNav role={role} />
        <div className="min-w-0 flex-1 overflow-auto">
          <Outlet />
        </div>
      </div>
    </div>
  )
}
