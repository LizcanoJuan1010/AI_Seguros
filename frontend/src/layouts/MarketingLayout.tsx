import { Outlet } from 'react-router-dom'
import { TopNav } from '../components/chrome/TopNav'

export function MarketingLayout() {
  return (
    <div className="min-h-svh bg-background text-on-surface">
      <TopNav variant="marketing" />
      <Outlet />
    </div>
  )
}
