import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': process.env.VITE_BACKEND_URL || 'http://localhost:8000' } },
})
