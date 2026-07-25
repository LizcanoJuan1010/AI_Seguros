import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import { RequireAuth } from './components/RequireAuth'
import { TenantProvider } from './tenant/TenantContext'
import { MarketingLayout } from './layouts/MarketingLayout'
import { AppShellLayout } from './layouts/AppShellLayout'
import { LandingPage } from './pages/LandingPage'
import { LoginPage } from './pages/LoginPage'
import { LiveAiCallPage } from './pages/LiveAiCallPage'
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
            {/* La bandeja del vendedor se fusionó en el panel del gerente:
                la pestaña "Clientes" muestra el mismo expediente 360. Enlaces y
                marcadores antiguos a /vendedor redirigen allí. */}
            <Route
              path="/vendedor"
              element={<Navigate to="/gerente?tab=clientes" replace />}
            />

            {/* Canal del cliente final: SIN login. El cliente no tiene usuario;
                su identidad es el device_id anónimo (lib/clientIdentity.ts) y
                entra directo al chat o a la llamada de voz. */}
            <Route element={<AppShellLayout />}>
              <Route path="/asistente" element={<AssistantPage />} />
              <Route path="/llamada" element={<LiveAiCallPage />} />
            </Route>

            {/* Rutas de staff (gerente): requieren sesión */}
            <Route element={<RequireAuth />}>
              <Route element={<AppShellLayout />}>
                <Route path="/gerente" element={<ManagerDashboardPage />} />
              </Route>
            </Route>

            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </TenantProvider>
      </AuthProvider>
    </BrowserRouter>
  )
}
