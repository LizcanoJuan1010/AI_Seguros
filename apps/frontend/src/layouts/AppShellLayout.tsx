import { Outlet } from 'react-router-dom'
import { TopNav } from '../components/chrome/TopNav'

export function AppShellLayout() {
  return (
    <div className="flex h-svh flex-col bg-mist-white text-on-surface">
      <TopNav variant="app" />
      <div className="min-h-0 w-full flex-1 overflow-auto">
        <Outlet />
      </div>
    </div>
  )
}
