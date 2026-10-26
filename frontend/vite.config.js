import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true
      },
      '/video_feed': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true
      },
      '/raw_feed': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true
      },
      '/captures': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true
      }
    }
  }
})
