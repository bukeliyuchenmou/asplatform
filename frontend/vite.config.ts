import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const apiProxyTarget = process.env.VITE_API_PROXY_TARGET || 'http://localhost:8002'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 7263,
    host: '0.0.0.0',
    proxy: {
      '/api': apiProxyTarget,
    },
  },
})
