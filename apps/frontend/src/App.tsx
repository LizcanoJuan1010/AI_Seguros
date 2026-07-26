import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import { RequireAuth } from './components/RequireAuth'
import { RequireRole } from './components/RequireRole'
import { TenantProvider } from './tenant/TenantContext'
import { MarketingLayout } from './layouts/MarketingLayout'
import { AppShellLayout } from './layouts/AppShellLayout'
import { ChatShellLayout } from './layouts/ChatShellLayout'
import { LandingPage } from './pages/LandingPage'
import { LoginPage } from './pages/LoginPage'
import { LiveAiCallPage } from './pages/LiveAiCallPage'
import { AgentLeadsPage } from './pages/AgentLeadsPage'
import { ManagerDashboardPage } from './pages/ManagerDashboardPage'
import { AssistantPage } from './pages/AssistantPage'
import { EmbedQuotePage } from './pages/EmbedQuotePage'
import { CampaignsPage } from './pages/CampaignsPage'
import { ChecklistPage } from './pages/ChecklistPage'

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
            {/* Checklist de activación: link enviado al cliente, sin auth */}
            <Route path="/activacion/:token" element={<ChecklistPage />} />
            {/* Sofía (chat web): pública — un lead nunca debería loguearse
                para hablar con el asistente. Si hay sesión activa (gerente
                probando, vendedor, etc.) el token igual viaja y el backend
                resuelve el rol; ver agent_core.resolve_identity. */}
            <Route element={<ChatShellLayout />}>
              <Route path="/asistente" element={<AssistantPage />} />
            </Route>

            {/* Rutas protegidas: requieren sesión (redirigen a /login si no) */}
            <Route element={<RequireAuth />}>
              <Route element={<AppShellLayout />}>
                <Route path="/llamada" element={<LiveAiCallPage />} />
                <Route path="/vendedor" element={<AgentLeadsPage />} />
                <Route path="/gerente" element={<ManagerDashboardPage />} />
                <Route element={<RequireRole roles={['GERENTE', 'ADMIN']} />}>
                  <Route path="/campanas" element={<CampaignsPage />} />
                </Route>
              </Route>
            </Route>

            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </TenantProvider>
      </AuthProvider>
    </BrowserRouter>
  )
}
