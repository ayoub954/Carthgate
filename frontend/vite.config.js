import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Local development only. /api is proxied to the FastAPI backend (uvicorn on :8000, or DIWANA_API if set).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': { target: process.env.DIWANA_API || 'http://127.0.0.1:8000', changeOrigin: true } },
  },
})
