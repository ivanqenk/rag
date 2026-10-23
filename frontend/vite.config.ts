/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: {
    // En desarrollo el navegador solo habla con Vite (puerto 5173), que reenvía /api al
    // backend. Así frontend y API comparten origen y no hace falta configurar CORS.
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    // jsdom es lento en equipos modestos (p. ej. CPU de portátil sobre WSL); el límite por
    // defecto de 5 s producía timeouts sin que fallara ninguna comprobación.
    testTimeout: 15_000,
  },
})
