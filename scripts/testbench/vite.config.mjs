// Testbench Vite config: serves frontend/ unchanged, with one difference from frontend/vite.config.js:
// /api is proxied to the backend, so API calls and audio URLs work from http://localhost:5173.
// scripts/testbench.py starts it with VITE_USE_MOCK=false and VITE_API_BASE_URL=http://localhost:5173, so the
// frontend's own client (frontend/src/api.js) calls the real backend through this proxy.
// Run through scripts/testbench.py, or from frontend/:  node node_modules/vite/bin/vite.js --config ../scripts/testbench/vite.config.mjs
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(here, '../../frontend')
// The React plugin lives in frontend/node_modules, not next to this file.
const { default: react } = await import(
  pathToFileURL(path.join(root, 'node_modules/@vitejs/plugin-react/dist/index.js')).href
)
const backend = process.env.TESTBENCH_BACKEND || 'http://127.0.0.1:8000'

export default {
  root,
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: { '/api': backend },
    fs: { allow: [root, here] },
  },
}
