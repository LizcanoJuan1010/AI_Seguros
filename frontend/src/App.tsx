import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { MarketingLayout } from './layouts/MarketingLayout'
import { CallLayout } from './layouts/CallLayout'
import { AppShellLayout } from './layouts/AppShellLayout'
import { LandingPage } from './pages/LandingPage'
import { LiveAiCallPage } from './pages/LiveAiCallPage'
import { AgentLeadsPage } from './pages/AgentLeadsPage'
import { ManagerDashboardPage } from './pages/ManagerDashboardPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<MarketingLayout />}>
          <Route path="/" element={<LandingPage />} />
        </Route>
        <Route element={<CallLayout />}>
          <Route path="/llamada" element={<LiveAiCallPage />} />
        </Route>
        <Route element={<AppShellLayout />}>
          <Route path="/vendedor" element={<AgentLeadsPage />} />
          <Route path="/gerente" element={<ManagerDashboardPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
