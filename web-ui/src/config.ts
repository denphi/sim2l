// Configuration for sim2l services
export const config = {
  services: {
    cache: {
      // Use Vite proxy in development to avoid CORS issues
      baseUrl: import.meta.env.VITE_CACHE_SERVICE_URL || '/api/cache',
      sessionId: import.meta.env.VITE_SESSION_ID || 'demo-session'
    },
    results: {
      baseUrl: import.meta.env.VITE_RESULTS_SERVICE_URL || '/api/results',
      sessionId: import.meta.env.VITE_SESSION_ID || 'demo-session'
    },
    catalog: {
      baseUrl: import.meta.env.VITE_CATALOG_SERVICE_URL || '/api/catalog',
      sessionId: import.meta.env.VITE_SESSION_ID || 'demo-session'
    }
  },
  polling: {
    healthCheckInterval: 10000,  // 10 seconds
    dataRefreshInterval: 30000   // 30 seconds
  }
};
