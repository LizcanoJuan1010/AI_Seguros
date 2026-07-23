import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const aiTarget = env.VITE_AI_URL || 'http://localhost:8085'

  return {
    plugins: [react(), tailwindcss()],
    server: {
      proxy: {
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
