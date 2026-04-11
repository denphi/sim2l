// Cache Service Types

export interface CacheEntry {
  cache_key: string;
  simulation_id: number;
  simulation_name: string;
  simulation_version: string;
  execution_id: string;
  squid_id: string;
  input_hash: string;
  created_at: string;
  last_accessed_at: string | null;
  access_count: number;
  hit_count: number;
  size_bytes?: number;
  status: 'valid' | 'invalidated';
  invalidated_at?: string | null;
  invalidation_reason?: string | null;
  metadata?: {
    inputs?: Record<string, any>;
    [key: string]: any;
  };
  run_db_path?: string;
}

export interface CacheStats {
  total_requests?: number;
  total_hits?: number;
  total_misses?: number;
  hit_rate_percent?: number;
  total_size_mb?: number;
  total_entries?: number;
  total_accesses?: number;
}

export interface CacheListResponse {
  entries: CacheEntry[];
  total: number;
  limit: number;
  offset: number;
}

export interface InvalidationFilters {
  simulation_id?: number;
  simulation_name?: string;
  simulation_version?: string;
  pattern?: string;
  reason?: string;
}

export interface InvalidationResult {
  invalidated_count: number;
}

export interface HealthStatus {
  status: 'healthy' | 'unhealthy';
  backend?: string;
  error?: string;
}
