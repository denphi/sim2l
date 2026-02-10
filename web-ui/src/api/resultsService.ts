// Results Service API Client
import { apiClient } from './client';
import type {
  ExecutionResult,
  ParameterStats,
  ResultsListResponse,
  SimulationSchema,
  SearchFilters,
} from '../types/results';

export class ResultsServiceClient {
  async healthCheck(): Promise<{ status: string; service: string; backend: string }> {
    const response = await apiClient.results.get('/health');
    return response.data;
  }

  async searchResults(filters: SearchFilters): Promise<ResultsListResponse> {
    const response = await apiClient.results.post<ResultsListResponse>('/search', filters);
    return response.data;
  }

  async getResult(executionId: string): Promise<ExecutionResult> {
    const response = await apiClient.results.get<ExecutionResult>(`/results/${executionId}`);
    return response.data;
  }

  async getParameterStats(simulationName: string, paramName: string): Promise<ParameterStats> {
    const response = await apiClient.results.get<ParameterStats>(
      `/stats/${simulationName}/${paramName}`
    );
    return response.data;
  }

  async listResults(params: {
    limit?: number;
    offset?: number;
    simulation?: string;
    version?: string;
    status?: string;
    input_filters?: Record<string, any>;
    output_filters?: Record<string, any>;
  } = {}): Promise<ResultsListResponse> {
    try {
      const response = await apiClient.results.get<ResultsListResponse>('/results', { params });
      return response.data;
    } catch (error) {
      console.warn('List results endpoint not available, using search');
      // Convert params to search filters format
      return this.searchResults({
        simulation_name: params.simulation,
        simulation_version: params.version,
        status: params.status,
        input_filters: params.input_filters,
        output_filters: params.output_filters,
        limit: params.limit || 100,
      });
    }
  }

  async getSchemas(): Promise<{ schemas: SimulationSchema[] }> {
    try {
      const response = await apiClient.results.get<{ schemas: SimulationSchema[] }>('/schemas');
      return response.data;
    } catch (error) {
      console.warn('Schemas endpoint not available');
      return { schemas: [] };
    }
  }

  async getRecentExecutions(limit: number = 10): Promise<{ executions: ExecutionResult[] }> {
    try {
      const response = await apiClient.results.get<{ executions: ExecutionResult[] }>(
        '/executions/recent',
        { params: { limit } }
      );
      return response.data;
    } catch (error) {
      console.warn('Recent executions endpoint not available');
      return { executions: [] };
    }
  }

  async getAllParameterStats(simulationName: string): Promise<{ stats: ParameterStats[] }> {
    try {
      const response = await apiClient.results.get<{ stats: ParameterStats[] }>(
        `/parameter-stats/${simulationName}`
      );
      return response.data;
    } catch (error) {
      console.warn('All parameter stats endpoint not available');
      return { stats: [] };
    }
  }
}

export const resultsService = new ResultsServiceClient();
