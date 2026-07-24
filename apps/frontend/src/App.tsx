import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import { RequireAuth } from './components/RequireAuth'
import { TenantProvider } from './tenant/TenantContext'
import { MarketingLayout } from './layouts/MarketingLayout'
import { AppShellLayout } from './layouts/AppShellLayout'
import { LandingPage } from './pages/LandingPage'
import { LoginPage } from './pages/LoginPage'
import { LiveAiCallPage } from './pages/LiveAiCallPage'
import { AgentLeadsPage } from './pages/AgentLeadsPage'
import { ManagerDashboardPage } from './pages/ManagerDashboardPage'
import { AssistantPage } from './pages/AssistantPage'
import { EmbedQuotePage } from './pages/EmbedQuotePage'

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <TenantProvider>
          <Routes>
            {/* Rutas públicas */}
            <Route element={<MarketingLayout />}>
              <Route path="/" element={<LandingPage />} />
            </Route>
            <Route path="/login" element={<LoginPage />} />
            {/* Widget embebible (iframe de aliados): sin nav, sin auth */}
            <Route path="/embed" element={<EmbedQuotePage />} />

            {/* Rutas protegidas: requieren sesión (redirigen a /login si no) */}
            <Route element={<RequireAuth />}>
              <Route element={<AppShellLayout />}>
                <Route path="/llamada" element={<LiveAiCallPage />} />
                <Route path="/vendedor" element={<AgentLeadsPage />} />
                <Route path="/gerente" element={<ManagerDashboardPage />} />
                <Route path="/asistente" element={<AssistantPage />} />
              </Route>
            </Route>

            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </TenantProvider>
      </AuthProvider>
    </BrowserRouter>
  )
}
