import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
// /api goes to the backend (uvicorn on port 8000), so the app and its audio URLs work from the Vite port.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': process.env.BACKEND_URL || 'http://127.0.0.1:8000' } },
})
