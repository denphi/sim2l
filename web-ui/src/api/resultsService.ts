// Results Service API Client
import { apiClient, serviceErrorMessage } from './client';
import type {
  ExecutionResult,
  ParameterStats,
  ResultsListResponse,
  SimulationSchema,
  SearchFilters,
  RunRequest,
  RunResponse,
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

  async deleteResult(executionId: string): Promise<{ status: string; execution_id: string }> {
    try {
      const response = await apiClient.results.delete<{ status?: string; execution_id?: string }>(
        `/results/${encodeURIComponent(executionId)}`
      );
      return {
        status: response.data.status || 'deleted',
        execution_id: response.data.execution_id || executionId,
      };
    } catch (error) {
      throw new Error(serviceErrorMessage(error, 'Failed to delete result'));
    }
  }

  async clearAllResults(): Promise<{ deleted: number }> {
    try {
      const response = await apiClient.results.delete<{ deleted: number }>('/results');
      return response.data;
    } catch (error) {
      throw new Error(serviceErrorMessage(error, 'Failed to clear results'));
    }
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
    // Results service currently provides POST /search for listing/filtering.
    // Call it directly to avoid expected 404 noise from probing GET /results.
    return this.searchResults({
      simulation_name: params.simulation,
      simulation_version: params.version,
      status: params.status,
      input_filters: params.input_filters,
      output_filters: params.output_filters,
      limit: params.limit || 100,
    });
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

  async submitRun(request: RunRequest): Promise<RunResponse> {
    try {
      const response = await apiClient.results.post<RunResponse>('/run', request);
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

export const resultsService = new ResultsServiceClient();
