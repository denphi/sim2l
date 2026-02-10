// Catalog Service API Client
import { apiClient } from './client';
import type {
  Simulation,
  ExecutionRecord,
  ExecutionStats,
  SyncRequest,
  OverviewStats,
} from '../types/catalog';

export class CatalogServiceClient {
  async healthCheck(): Promise<{ status: string }> {
    const response = await apiClient.catalog.get('/health');
    return response.data;
  }

  async searchSimulations(query: string = ''): Promise<{ simulations: Simulation[] } | Simulation[]> {
    const response = await apiClient.catalog.get<Simulation[] | { simulations: Simulation[] }>(
      '/simulations/search',
      { params: { query } }
    );
    return response.data;
  }

  async getSimulation(name: string, version?: string): Promise<Simulation> {
    const params = version ? { version } : {};
    const response = await apiClient.catalog.get<Simulation>(`/simulations/${name}`, { params });
    return response.data;
  }

  async getExecutionStats(simulationId: number): Promise<ExecutionStats> {
    const response = await apiClient.catalog.get<ExecutionStats>(
      `/simulations/${simulationId}/stats`
    );
    return response.data;
  }

  async getPendingSync(installationId?: string): Promise<{ requests: SyncRequest[] }> {
    const params = installationId ? { installation_id: installationId } : {};
    const response = await apiClient.catalog.get<{ requests: SyncRequest[] }>('/sync/pending', {
      params,
    });
    return response.data;
  }

  async approveSync(requestId: number): Promise<{ status: string; simulation_id: number }> {
    const response = await apiClient.catalog.post<{ status: string; simulation_id: number }>(
      `/sync/${requestId}/approve`
    );
    return response.data;
  }

  async getPopularSimulations(limit: number = 10): Promise<{ simulations: Simulation[] }> {
    try {
      const response = await apiClient.catalog.get<{ simulations: Simulation[] }>(
        '/simulations/popular',
        { params: { limit } }
      );
      return response.data;
    } catch (error) {
      console.warn('Popular simulations endpoint not available');
      return { simulations: [] };
    }
  }

  async listExecutions(params: {
    limit?: number;
    offset?: number;
    simulation_id?: number;
  } = {}): Promise<{
    executions: ExecutionRecord[];
    total: number;
    limit: number;
    offset: number;
  }> {
    try {
      const response = await apiClient.catalog.get('/executions', { params });
      return response.data;
    } catch (error) {
      console.warn('List executions endpoint not available');
      return { executions: [], total: 0, limit: 25, offset: 0 };
    }
  }

  async getOverviewStats(): Promise<OverviewStats> {
    try {
      const response = await apiClient.catalog.get<OverviewStats>('/statistics/overview');
      return response.data;
    } catch (error) {
      console.warn('Overview stats endpoint not available');
      return {
        total_simulations: 0,
        active_simulations: 0,
        total_executions: 0,
        successful_executions: 0,
        cached_executions: 0,
      };
    }
  }
}

export const catalogService = new CatalogServiceClient();
