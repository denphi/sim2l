// Catalog Service API Client
import { apiClient, serviceErrorMessage } from './client';
import { getSessionId } from './session';
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

  async searchSimulations(query: string = ''): Promise<Simulation[]> {
    // The catalog `/simulations/search` endpoint returns a flat array
    // (review item #W3). Some legacy mock servers responded with
    // `{ simulations: [...] }`, so we normalise both shapes here rather
    // than pushing the discriminator out to every caller.
    const response = await apiClient.catalog.get<
      Simulation[] | { simulations: Simulation[] }
    >('/simulations/search', { params: { query } });
    const data = response.data;
    if (Array.isArray(data)) return data;
    return data?.simulations ?? [];
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
    try {
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
    } catch (error) {
      throw new Error(serviceErrorMessage(error, 'Failed to delete simulation'));
    }
  }

  async clearAllSimulations(): Promise<{ deleted: number }> {
    try {
      const response = await apiClient.catalog.delete<{ deleted: number }>('/simulations');
      return response.data;
    } catch (error) {
      throw new Error(serviceErrorMessage(error, 'Failed to clear simulations'));
    }
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
      const response = await apiClient.catalog.post<RunResponse>('/run', request, {
        headers: {
          'X-Sim2L-Cache-Session-ID': getSessionId('cache'),
          'X-Sim2L-Results-Session-ID': getSessionId('results'),
        },
      });
      return response.data;
    } catch (error: any) {
      console.error('Error submitting run:', error);
      return {
        success: false,
        error: serviceErrorMessage(error, 'Failed to submit run'),
      };
    }
  }
}

export const catalogService = new CatalogServiceClient();
