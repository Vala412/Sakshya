// `defineConfig` from vitest/config rather than vite: it is the same
// function widened to accept the `test` block, which vite's own type does
// not know about.
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5173,
    // Proxy keeps the browser on one origin in development, so the app can
    // use same-origin relative URLs ('/api/...') in both dev and production.
    // Without it the client would need an environment-dependent base URL.
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    css: false,
  },
})
