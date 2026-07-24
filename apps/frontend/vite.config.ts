import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const aiTarget = env.VITE_AI_URL || 'http://localhost:8085'
  const backendTarget = env.VITE_BACKEND_URL || 'http://localhost:3001'

  return {
    plugins: [react(), tailwindcss()],
    server: {
      proxy: {
        // Dominio NestJS (auth, teams, leads, dashboard). Prefijo más
        // específico primero: gana sobre '/api'. ws:true además reenvía el
        // handshake del gateway de la llamada en vivo (/api/v1/live-call).
        '/api/v1': {
          target: backendTarget,
          changeOrigin: true,
          ws: true,
        },
        // Servicio IA (FastAPI): chat SSE, documentos, productos, insights.
        // El frontend habla siempre contra rutas relativas /api/* y Vite las
        // reenvía al servicio IA. Cambiable por env VITE_AI_URL (default 8085).
        '/api': {
          target: aiTarget,
          changeOrigin: true,
          ws: false,
        },
      },
    },
  }
})
