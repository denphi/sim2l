// Cache Service API Client
import { apiClient } from './client';
import type {
  CacheEntry,
  CacheStats,
  CacheListResponse,
  InvalidationFilters,
  InvalidationResult,
  HealthStatus,
} from '../types/cache';

export class CacheServiceClient {
  async healthCheck(): Promise<HealthStatus> {
    const response = await apiClient.cache.get<HealthStatus>('/health');
    return response.data;
  }

  async getEntry(cacheKey: string): Promise<CacheEntry | null> {
    try {
      const response = await apiClient.cache.get<CacheEntry>(`/${cacheKey}`);
      return response.data;
    } catch (error: any) {
      if (error.response?.status === 404) {
        return null;
      }
      throw error;
    }
  }

  async listEntries(params: {
    limit?: number;
    offset?: number;
    simulation_id?: number;
    simulation_name?: string;
    status?: 'valid' | 'invalidated';
  } = {}): Promise<CacheListResponse> {
    const response = await apiClient.cache.get<CacheListResponse>('/cache/entries', { params });
    return response.data;
  }

  async getStats(simulationId?: number): Promise<CacheStats> {
    const params = simulationId ? { simulation_id: simulationId } : {};
    const response = await apiClient.cache.get<CacheStats>('/cache/stats', { params });
    return response.data;
  }

  async invalidate(filters: InvalidationFilters): Promise<InvalidationResult> {
    const response = await apiClient.cache.post<InvalidationResult>('/cache/invalidate', filters);
    return response.data;
  }

  async deleteEntry(cacheKey: string): Promise<{ status: string; cache_key: string }> {
    const response = await apiClient.cache.delete<{ status?: string; cache_key?: string }>(
      `/cache/${encodeURIComponent(cacheKey)}`
    );
    return {
      status: response.data.status || 'deleted',
      cache_key: response.data.cache_key || cacheKey,
    };
  }

  async getHotEntries(limit: number = 10): Promise<{ entries: CacheEntry[] }> {
    try {
      const response = await apiClient.cache.get<{ entries: CacheEntry[] }>('/cache/hot', {
        params: { limit },
      });
      return response.data;
    } catch (error) {
      // If endpoint doesn't exist yet, return empty
      console.warn('Hot entries endpoint not available');
      return { entries: [] };
    }
  }
}

export const cacheService = new CacheServiceClient();
