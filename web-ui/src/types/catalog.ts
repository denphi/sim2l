// Catalog Service Types

export interface Simulation {
  id: number;
  name: string;
  version: string;
  description: string;
  author?: string;
  organization?: string;
  tags?: string[];
  status: 'active' | 'deprecated' | 'archived';
  input_schema?: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export interface ExecutionRecord {
  execution_id: string;
  squid_id: string;
  simulation_id: number;
  status: string;
  duration_seconds: number;
  started_at: string;
  completed_at: string;
  cache_hit: boolean;
}

export interface ExecutionStats {
  total_executions: number;
  successful: number;
  failed: number;
  cached: number;
  avg_duration: number;
  min_duration: number;
  max_duration: number;
}

export interface SyncRequest {
  id: number;
  installation_id: string;
  operation: string;
  status: 'pending' | 'approved' | 'rejected';
  created_at: string;
  processed_at?: string;
}

export interface OverviewStats {
  total_simulations: number;
  active_simulations: number;
  total_executions: number;
  successful_executions: number;
  cached_executions: number;
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
