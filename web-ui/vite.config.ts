import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined;
          if (
            id.includes('/react/') ||
            id.includes('/react-dom/') ||
            id.includes('/react-router-dom/') ||
            id.includes('/react-redux/') ||
            id.includes('/@reduxjs/toolkit/')
          ) {
            return 'vendor-react';
          }
          if (
            id.includes('/@mui/') ||
            id.includes('/@emotion/')
          ) {
            return 'vendor-mui';
          }
          if (id.includes('/recharts/')) {
            return 'vendor-charts';
          }
          if (
            id.includes('/axios/') ||
            id.includes('/date-fns/') ||
            id.includes('/react-hook-form/') ||
            id.includes('/zod/')
          ) {
            return 'vendor-utils';
          }
          return 'vendor';
        },
      },
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/api/cache': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/cache/, ''),
        configure: (proxy, _options) => {
          proxy.on('error', (err, _req, _res) => {
            console.log('proxy error', err);
          });
          proxy.on('proxyReq', (_proxyReq, req, _res) => {
            console.log('Sending Request to cache:', req.method, req.url);
          });
        },
      },
      '/api/results': {
        target: 'http://localhost:8003',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/results/, ''),
        configure: (proxy, _options) => {
          proxy.on('proxyReq', (_proxyReq, req, _res) => {
            console.log('Sending Request to results:', req.method, req.url);
          });
        },
      },
      '/api/catalog': {
        target: 'http://localhost:8002',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/catalog/, ''),
        configure: (proxy, _options) => {
          proxy.on('proxyReq', (_proxyReq, req, _res) => {
            console.log('Sending Request to catalog:', req.method, req.url);
          });
        },
      }
    }
  }
})
