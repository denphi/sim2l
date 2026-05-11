// Catalog Service API Client
import { apiClient } from './client';
import type {
  Simulation,
  ExecutionRecord,
  ExecutionStats,
  SyncRequest,
  OverviewStats,
  RunRequest,
  RunResponse,
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

  async deleteSimulation(simulationId: number): Promise<{
    status: string;
    simulation_id: number;
    name?: string;
    version?: string;
  }> {
    const response = await apiClient.catalog.delete<{
      status?: string;
      simulation_id?: number;
      name?: string;
      version?: string;
    }>(`/simulations/${simulationId}`);
    return {
      status: response.data.status || 'deleted',
      simulation_id: response.data.simulation_id || simulationId,
      name: response.data.name,
      version: response.data.version,
    };
  }

  async clearAllSimulations(): Promise<{ deleted: number }> {
    const response = await apiClient.catalog.delete<{ deleted: number }>('/simulations');
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
    };
  }

  async submitRun(request: RunRequest): Promise<RunResponse> {
    try {
      const response = await apiClient.catalog.post<RunResponse>('/run', request);
      return response.data;
    } catch (error: any) {
      console.error('Error submitting run:', error);
      return {
        success: false,
        error: error.response?.data?.error || error.message || 'Failed to submit run',
      };
    }
  }
}

export const catalogService = new CatalogServiceClient();
