// Base HTTP client for all sim2l services.
//
// Each axios instance is bound to a single service (cache/catalog/results)
// and reads the corresponding session token from sessionStorage at send-time.
// This lets a single login mint distinct session tokens per backend (review
// item #T1) while keeping the request interceptor stateless.
//
// Network-error retries were removed (#W2): silently doubling the user's
// wait on a failing service was confusing. The 401 → refresh-and-retry
// path coalesces concurrent refreshes (so a single dead session doesn't
// fan out into N refresh calls) and returns null on persistent failure
// (review item #T11) so the caller falls through to the login modal
// instead of replaying with a known-dead id.
import axios, { AxiosInstance, AxiosRequestConfig, AxiosError } from 'axios';
import { config } from '../config';
import {
  Service,
  clearSessionIds,
  getSessionId,
  notifySessionInvalid,
  setSessionId,
} from './session';

type RetryableRequestConfig = AxiosRequestConfig & { _refreshRetry?: boolean };

export class ApiClient {
  private clients: Record<Service, AxiosInstance>;
  private refreshInFlight: Promise<string | null> | null = null;

  constructor() {
    this.clients = {
      cache: this.createClient('cache', config.services.cache.baseUrl),
      results: this.createClient('results', config.services.results.baseUrl),
      catalog: this.createClient('catalog', config.services.catalog.baseUrl),
    };
  }

  private createClient(service: Service, baseURL: string): AxiosInstance {
    const client = axios.create({
      baseURL,
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    client.interceptors.request.use(
      reqConfig => {
        reqConfig.headers = reqConfig.headers ?? {};
        (reqConfig.headers as Record<string, string>)['X-Session-ID'] =
          getSessionId(service);
        console.log(
          `[API:${service}] ${reqConfig.method?.toUpperCase()} ${reqConfig.url}`
        );
        return reqConfig;
      },
      error => {
        console.error(`[API:${service}] Request error:`, error);
        return Promise.reject(error);
      }
    );

    client.interceptors.response.use(
      response => {
        console.log(
          `[API:${service}] Response ${response.status} from ${response.config.url}`
        );
        return response;
      },
      async (error: AxiosError) => {
        const original = error.config as RetryableRequestConfig | undefined;
        if (error.response?.status === 403) {
          clearSessionIds();
          notifySessionInvalid();
        }
        if (
          error.response?.status === 401 &&
          original &&
          !original._refreshRetry
        ) {
          if (service !== 'catalog') {
            clearSessionIds();
            notifySessionInvalid();
            return Promise.reject(error);
          }
          original._refreshRetry = true;
          const newSessionId = await this.refreshSession(service);
          if (newSessionId) {
            // Replay with the fresh token; the request interceptor will
            // pick it up automatically from sessionStorage.
            return client.request(original);
          }
          // Refresh failed — let the app react (eg. show the login modal).
          notifySessionInvalid();
        }
        console.error(`[API:${service}] Response error:`, error);
        return Promise.reject(error);
      }
    );

    return client;
  }

  /**
   * Coalesce concurrent refresh attempts: when multiple in-flight requests
   * fail with 401 at the same time, only one POST /session/refresh fires.
   *
   * Returns `null` if the refresh endpoint reports the session is gone
   * (#T11) — the caller then surfaces a "please log in" prompt instead of
   * looping with the same dead id.
   */
  private refreshSession(service: Service): Promise<string | null> {
    if (this.refreshInFlight) return this.refreshInFlight;
    this.refreshInFlight = (async () => {
      try {
        // /session/refresh only exists on the catalog today, so we use the
        // catalog's session id as the lookup key. A future improvement
        // would be to ask each service to refresh its own session.
        const resp = await axios.post<{ token?: string; session_id?: string }>(
          `${config.services.catalog.baseUrl}/session/refresh`,
          null,
          {
            headers: { 'X-Session-ID': getSessionId('catalog') },
            timeout: 10000,
          }
        );
        const fresh = resp.data?.token || resp.data?.session_id;
        if (fresh) {
          setSessionId('catalog', fresh);
          return fresh;
        }
        // 200 with no id — server kept the same session, no change needed.
        return getSessionId(service);
      } catch (err) {
        // 401/404/network: caller should treat this as "session is gone".
        console.warn(`[API:${service}] Session refresh failed`, err);
        return null;
      } finally {
        this.refreshInFlight = null;
      }
    })();
    return this.refreshInFlight;
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

export const apiClient = new ApiClient();

export function serviceErrorMessage(error: unknown, fallback: string): string {
  if (axios.isAxiosError<{ error?: string }>(error)) {
    const detail = error.response?.data?.error;
    if (error.response?.status === 403) {
      return detail
        ? `${detail}. Sign in with an account that has permission for this operation.`
        : 'Insufficient privileges. Sign in with an account that has permission for this operation.';
    }
    if (error.response?.status === 401) {
      return detail
        ? `${detail}. Sign in again and retry.`
        : 'Session expired or missing. Sign in again and retry.';
    }
    if (detail) return detail;
    if (error.message) return error.message;
  }
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}
