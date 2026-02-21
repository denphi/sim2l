// Results Service Types

export interface ExecutionResult {
  execution_id: string;
  simulation_name: string;
  simulation_version: string;
  squid_id: string;
  status: 'completed' | 'failed' | 'running';
  duration_seconds?: number;
  execution_time_ms?: number;
  started_at?: string;
  completed_at?: string;
  created_at: string;
  cache_hit?: boolean;
  input_params?: Record<string, any>;
  output_params?: Record<string, any>;
}

export interface ParameterStats {
  param_name: string;
  min_value: number;
  max_value: number;
  avg_value: number;
  count: number;
}

export interface ResultsListResponse {
  results: ExecutionResult[];
  total: number;
  limit: number;
  offset: number;
}

export interface SimulationSchema {
  name: string;
  version: string;
  schema: {
    input: Record<string, any>;
    output: Record<string, any>;
  };
}

export interface SearchFilters {
  simulation_name?: string;
  simulation_version?: string;
  status?: string;
  input_filters?: Record<string, any>;
  output_filters?: Record<string, any>;
  limit?: number;
  offset?: number;
}

export interface RunRequest {
  simulation_name: string;
  version?: string;
  params: Record<string, any>;
}

export interface RunResponse {
  success: boolean;
  execution_id?: string;
  squid_id?: string;
  status?: string;
  duration_seconds?: number;
  outputs?: Record<string, any>;
  error?: string;
}
