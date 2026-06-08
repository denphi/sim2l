// Cache Service API Client
import { apiClient, serviceErrorMessage } from './client';
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
    try {
      const response = await apiClient.cache.post<InvalidationResult>('/cache/invalidate', filters);
      return response.data;
    } catch (error) {
      throw new Error(serviceErrorMessage(error, 'Failed to invalidate cache entries'));
    }
  }

  async deleteEntry(cacheKey: string): Promise<{ status: string; cache_key: string }> {
    try {
      const response = await apiClient.cache.delete<{ status?: string; cache_key?: string }>(
        `/cache/${encodeURIComponent(cacheKey)}`
      );
      return {
        status: response.data.status || 'deleted',
        cache_key: response.data.cache_key || cacheKey,
      };
    } catch (error) {
      throw new Error(serviceErrorMessage(error, 'Failed to delete cache entry'));
    }
  }

  async clearAllEntries(): Promise<{ deleted: number }> {
    try {
      const response = await apiClient.cache.delete<{ deleted: number }>('/cache');
      return response.data;
    } catch (error) {
      throw new Error(serviceErrorMessage(error, 'Failed to clear cache entries'));
    }
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
