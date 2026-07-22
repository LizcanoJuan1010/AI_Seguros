import { Outlet } from 'react-router-dom'

export function CallLayout() {
  return (
    <div className="flex min-h-svh flex-col bg-background text-on-background selection:bg-primary-fixed selection:text-on-primary-fixed">
      <Outlet />
    </div>
  )
}
