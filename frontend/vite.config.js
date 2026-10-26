import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  base: '/app/',   // la API sirve el build bajo /app
  // En desarrollo (npm run dev) las llamadas /api pasan a la API local.
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
