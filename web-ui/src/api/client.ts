// Base HTTP client for all sim2l services
import axios, { AxiosInstance, AxiosRequestConfig } from 'axios';
import { config } from '../config';

export class ApiClient {
  private clients: Record<string, AxiosInstance>;

  constructor() {
    this.clients = {
      cache: this.createClient(config.services.cache.baseUrl, config.services.cache.sessionId),
      results: this.createClient(config.services.results.baseUrl, config.services.results.sessionId),
      catalog: this.createClient(config.services.catalog.baseUrl, config.services.catalog.sessionId),
    };
  }

  private createClient(baseURL: string, sessionId: string): AxiosInstance {
    const client = axios.create({
      baseURL,
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
        'X-Session-ID': sessionId,
      },
    });

    // Request interceptor
    client.interceptors.request.use(
      (config) => {
        console.log(`[API] ${config.method?.toUpperCase()} ${config.url}`);
        return config;
      },
      (error) => {
        console.error('[API] Request error:', error);
        return Promise.reject(error);
      }
    );

    // Response interceptor
    client.interceptors.response.use(
      (response) => {
        console.log(`[API] Response ${response.status} from ${response.config.url}`);
        return response;
      },
      async (error) => {
        console.error('[API] Response error:', error);

        // Retry logic for network errors
        if (error.code === 'ECONNABORTED' || error.message === 'Network Error') {
          console.log('[API] Network error, retrying...');
          const originalRequest = error.config as AxiosRequestConfig & { _retry?: boolean };

          if (!originalRequest._retry) {
            originalRequest._retry = true;
            return client.request(originalRequest);
          }
        }

        return Promise.reject(error);
      }
    );

    return client;
  }

  get cache(): AxiosInstance {
    return this.clients.cache;
  }

  get results(): AxiosInstance {
    return this.clients.results;
  }

  get catalog(): AxiosInstance {
    return this.clients.catalog;
  }

  // Health check for all services
  async checkAllServices(): Promise<Record<string, any>> {
    const checks = await Promise.allSettled([
      this.cache.get('/health'),
      this.results.get('/health'),
      this.catalog.get('/health'),
    ]);

    return {
      cache: checks[0].status === 'fulfilled' ? checks[0].value.data : { status: 'unhealthy', error: 'Connection failed' },
      results: checks[1].status === 'fulfilled' ? checks[1].value.data : { status: 'unhealthy', error: 'Connection failed' },
      catalog: checks[2].status === 'fulfilled' ? checks[2].value.data : { status: 'unhealthy', error: 'Connection failed' },
    };
  }
}

// Export a singleton instance
export const apiClient = new ApiClient();
