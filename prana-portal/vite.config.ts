import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  test: {
    globals: true,
    environment: 'jsdom',
    // jsdom defaults to the opaque origin "about:blank", where the Storage API
    // (localStorage/sessionStorage) is unavailable per browser origin rules —
    // window.localStorage silently resolves to undefined with no url set here.
    // A concrete origin is required for any test exercising persisted state
    // (e.g. the zustand `persist` stores in src/store/).
    environmentOptions: {
      jsdom: { url: 'http://localhost:3000' },
    },
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
  plugins: [react()],
  // VITE_BASE_PATH is set by the GitHub Actions deploy workflow to /<repo-name>/
  // Defaults to '/' for local dev.
  base: process.env.VITE_BASE_PATH ?? '/',
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: process.env.VITE_API_URL ?? 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
    },
  },
})
