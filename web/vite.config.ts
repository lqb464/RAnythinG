import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: '/app/',
  build: {
    outDir: '../src/rag_app/static/web',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      // Match .env PORT (default standalone 8000)
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
