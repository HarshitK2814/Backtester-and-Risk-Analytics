import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        timeout:      0,        // no socket timeout — SSE streams stay open
        proxyTimeout: 0,        // no outgoing timeout — data fetch can take time
      },
    },
  },
})
