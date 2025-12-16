-- Cache Service Database Schema (PostgreSQL or Redis alternative)
-- Centralized cache for distributed sim2l installations

-- Cache entries
CREATE TABLE IF NOT EXISTS cache_entries (
    cache_key TEXT PRIMARY KEY,
    simulation_id INTEGER NOT NULL,
    simulation_name TEXT NOT NULL,
    simulation_version TEXT NOT NULL,
    execution_id TEXT NOT NULL,
    squid_id TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    run_db_path TEXT, -- Path to per-run database
    user_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP, -- NULL = no expiration
    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    access_count INTEGER DEFAULT 1,
    hit_count INTEGER DEFAULT 0,
    size_bytes BIGINT,
    status TEXT DEFAULT 'valid', -- 'valid', 'invalidated', 'expired'
    metadata JSONB
);

-- Cache invalidation tracking
CREATE TABLE IF NOT EXISTS cache_invalidations (
    id SERIAL PRIMARY KEY,
    simulation_id INTEGER,
    simulation_name TEXT,
    simulation_version TEXT,
    invalidation_type TEXT NOT NULL, -- 'simulation', 'version', 'all', 'pattern'
    invalidation_pattern TEXT, -- Pattern for selective invalidation
    invalidated_count INTEGER DEFAULT 0,
    requested_by TEXT, -- Session ID
    requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reason TEXT
);

-- Cache statistics (aggregated)
CREATE TABLE IF NOT EXISTS cache_stats (
    id SERIAL PRIMARY KEY,
    period_start TIMESTAMP NOT NULL,
    period_end TIMESTAMP NOT NULL,
    simulation_id INTEGER,
    total_requests INTEGER DEFAULT 0,
    cache_hits INTEGER DEFAULT 0,
    cache_misses INTEGER DEFAULT 0,
    hit_rate REAL DEFAULT 0,
    avg_response_time_ms REAL,
    total_size_bytes BIGINT DEFAULT 0,
    evictions INTEGER DEFAULT 0,
    UNIQUE(period_start, period_end, simulation_id)
);

-- Cache access log (for analytics)
CREATE TABLE IF NOT EXISTS cache_access_log (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    cache_key TEXT NOT NULL,
    operation TEXT NOT NULL, -- 'get', 'set', 'invalidate', 'evict'
    hit BOOLEAN,
    session_id TEXT,
    user_id INTEGER,
    simulation_id INTEGER,
    response_time_ms REAL,
    metadata JSONB
);

-- Cache policy configuration
CREATE TABLE IF NOT EXISTS cache_policies (
    id SERIAL PRIMARY KEY,
    simulation_id INTEGER,
    policy_name TEXT NOT NULL,
    policy_type TEXT NOT NULL, -- 'ttl', 'lru', 'size', 'custom'
    ttl_seconds INTEGER, -- Time-to-live
    max_size_mb INTEGER, -- Max cache size
    max_entries INTEGER, -- Max number of entries
    priority INTEGER DEFAULT 0, -- Higher priority = less likely to evict
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB,
    UNIQUE(simulation_id, policy_name)
);

-- Session-based access control
CREATE TABLE IF NOT EXISTS cache_sessions (
    session_id TEXT PRIMARY KEY,
    user_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    access_level TEXT DEFAULT 'read', -- 'read', 'write', 'admin'
    is_valid BOOLEAN DEFAULT true,
    metadata JSONB
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_cache_entries_simulation ON cache_entries(simulation_id);
CREATE INDEX IF NOT EXISTS idx_cache_entries_squid ON cache_entries(squid_id);
CREATE INDEX IF NOT EXISTS idx_cache_entries_user ON cache_entries(user_id);
CREATE INDEX IF NOT EXISTS idx_cache_entries_created ON cache_entries(created_at);
CREATE INDEX IF NOT EXISTS idx_cache_entries_accessed ON cache_entries(last_accessed);
CREATE INDEX IF NOT EXISTS idx_cache_entries_status ON cache_entries(status);
CREATE INDEX IF NOT EXISTS idx_cache_access_log_timestamp ON cache_access_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_cache_access_log_key ON cache_access_log(cache_key);
CREATE INDEX IF NOT EXISTS idx_cache_sessions_expires ON cache_sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_cache_invalidations_simulation ON cache_invalidations(simulation_id);

-- Partitioning for cache_access_log (by date)
-- Uncomment if using PostgreSQL 10+
-- CREATE TABLE cache_access_log_template (LIKE cache_access_log INCLUDING ALL);
-- ALTER TABLE cache_access_log_template ADD CONSTRAINT cache_access_log_timestamp_check
--     CHECK (timestamp >= CURRENT_DATE AND timestamp < CURRENT_DATE + INTERVAL '1 day');

-- Views
CREATE OR REPLACE VIEW cache_stats_summary AS
SELECT
    simulation_id,
    SUM(total_requests) as total_requests,
    SUM(cache_hits) as total_hits,
    SUM(cache_misses) as total_misses,
    CASE
        WHEN SUM(total_requests) > 0 THEN
            ROUND(100.0 * SUM(cache_hits) / SUM(total_requests), 2)
        ELSE 0
    END as hit_rate_percent,
    AVG(avg_response_time_ms) as avg_response_time_ms,
    SUM(total_size_bytes) / (1024.0 * 1024.0) as total_size_mb
FROM cache_stats
WHERE period_start >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY simulation_id;

CREATE OR REPLACE VIEW cache_entries_active AS
SELECT
    ce.cache_key,
    ce.simulation_id,
    ce.simulation_name,
    ce.simulation_version,
    ce.execution_id,
    ce.squid_id,
    ce.created_at,
    ce.last_accessed,
    ce.access_count,
    ce.size_bytes / (1024.0 * 1024.0) as size_mb,
    EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - ce.last_accessed)) / 3600 as hours_since_last_access
FROM cache_entries ce
WHERE ce.status = 'valid'
AND (ce.expires_at IS NULL OR ce.expires_at > CURRENT_TIMESTAMP)
ORDER BY ce.last_accessed DESC;

CREATE OR REPLACE VIEW cache_hottest_entries AS
SELECT
    ce.cache_key,
    ce.simulation_name,
    ce.simulation_version,
    ce.access_count,
    ce.hit_count,
    ce.last_accessed,
    EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - ce.created_at)) / 86400 as age_days
FROM cache_entries ce
WHERE ce.status = 'valid'
AND ce.access_count > 5
ORDER BY ce.access_count DESC
LIMIT 100;

-- Functions
CREATE OR REPLACE FUNCTION get_cache_entry(
    p_cache_key TEXT,
    p_session_id TEXT
) RETURNS TABLE (
    execution_id TEXT,
    squid_id TEXT,
    run_db_path TEXT,
    metadata JSONB
) AS $$
BEGIN
    -- Check session validity
    IF NOT EXISTS (
        SELECT 1 FROM cache_sessions
        WHERE session_id = p_session_id
        AND is_valid = true
        AND expires_at > CURRENT_TIMESTAMP
    ) THEN
        RAISE EXCEPTION 'Invalid or expired session';
    END IF;

    -- Update access statistics
    UPDATE cache_entries
    SET
        last_accessed = CURRENT_TIMESTAMP,
        access_count = access_count + 1,
        hit_count = hit_count + 1
    WHERE cache_key = p_cache_key
    AND status = 'valid'
    AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP);

    -- Log access
    INSERT INTO cache_access_log (cache_key, operation, hit, session_id)
    VALUES (p_cache_key, 'get', true, p_session_id);

    -- Return cache entry
    RETURN QUERY
    SELECT
        ce.execution_id,
        ce.squid_id,
        ce.run_db_path,
        ce.metadata
    FROM cache_entries ce
    WHERE ce.cache_key = p_cache_key
    AND ce.status = 'valid'
    AND (ce.expires_at IS NULL OR ce.expires_at > CURRENT_TIMESTAMP);
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION set_cache_entry(
    p_cache_key TEXT,
    p_simulation_id INTEGER,
    p_simulation_name TEXT,
    p_simulation_version TEXT,
    p_execution_id TEXT,
    p_squid_id TEXT,
    p_input_hash TEXT,
    p_run_db_path TEXT,
    p_session_id TEXT,
    p_ttl_seconds INTEGER DEFAULT NULL,
    p_metadata JSONB DEFAULT NULL
) RETURNS BOOLEAN AS $$
DECLARE
    v_user_id INTEGER;
    v_expires_at TIMESTAMP;
BEGIN
    -- Check session validity and get user
    SELECT user_id INTO v_user_id
    FROM cache_sessions
    WHERE session_id = p_session_id
    AND is_valid = true
    AND expires_at > CURRENT_TIMESTAMP
    AND access_level IN ('write', 'admin');

    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'Invalid session or insufficient privileges';
    END IF;

    -- Calculate expiration
    IF p_ttl_seconds IS NOT NULL THEN
        v_expires_at := CURRENT_TIMESTAMP + (p_ttl_seconds || ' seconds')::INTERVAL;
    ELSE
        v_expires_at := NULL;
    END IF;

    -- Insert or update cache entry
    INSERT INTO cache_entries (
        cache_key,
        simulation_id,
        simulation_name,
        simulation_version,
        execution_id,
        squid_id,
        input_hash,
        run_db_path,
        user_id,
        expires_at,
        metadata
    ) VALUES (
        p_cache_key,
        p_simulation_id,
        p_simulation_name,
        p_simulation_version,
        p_execution_id,
        p_squid_id,
        p_input_hash,
        p_run_db_path,
        v_user_id,
        v_expires_at,
        p_metadata
    )
    ON CONFLICT (cache_key) DO UPDATE SET
        execution_id = EXCLUDED.execution_id,
        squid_id = EXCLUDED.squid_id,
        run_db_path = EXCLUDED.run_db_path,
        user_id = EXCLUDED.user_id,
        expires_at = EXCLUDED.expires_at,
        last_accessed = CURRENT_TIMESTAMP,
        access_count = cache_entries.access_count + 1,
        metadata = EXCLUDED.metadata,
        status = 'valid';

    -- Log access
    INSERT INTO cache_access_log (cache_key, operation, hit, session_id, user_id, simulation_id)
    VALUES (p_cache_key, 'set', false, p_session_id, v_user_id, p_simulation_id);

    RETURN true;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION invalidate_cache(
    p_simulation_id INTEGER DEFAULT NULL,
    p_simulation_name TEXT DEFAULT NULL,
    p_simulation_version TEXT DEFAULT NULL,
    p_pattern TEXT DEFAULT NULL,
    p_session_id TEXT DEFAULT NULL,
    p_reason TEXT DEFAULT NULL
) RETURNS INTEGER AS $$
DECLARE
    v_invalidated_count INTEGER;
BEGIN
    -- Invalidate matching entries
    UPDATE cache_entries
    SET
        status = 'invalidated',
        metadata = jsonb_set(
            COALESCE(metadata, '{}'::jsonb),
            '{invalidation_reason}',
            to_jsonb(COALESCE(p_reason, 'Manual invalidation'))
        )
    WHERE
        (p_simulation_id IS NULL OR simulation_id = p_simulation_id)
        AND (p_simulation_name IS NULL OR simulation_name = p_simulation_name)
        AND (p_simulation_version IS NULL OR simulation_version = p_simulation_version)
        AND (p_pattern IS NULL OR cache_key LIKE p_pattern)
        AND status = 'valid';

    GET DIAGNOSTICS v_invalidated_count = ROW_COUNT;

    -- Log invalidation
    INSERT INTO cache_invalidations (
        simulation_id,
        simulation_name,
        simulation_version,
        invalidation_type,
        invalidation_pattern,
        invalidated_count,
        requested_by,
        reason
    ) VALUES (
        p_simulation_id,
        p_simulation_name,
        p_simulation_version,
        CASE
            WHEN p_pattern IS NOT NULL THEN 'pattern'
            WHEN p_simulation_id IS NOT NULL THEN 'simulation'
            ELSE 'all'
        END,
        p_pattern,
        v_invalidated_count,
        p_session_id,
        p_reason
    );

    RETURN v_invalidated_count;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION evict_expired_entries() RETURNS INTEGER AS $$
DECLARE
    v_evicted_count INTEGER;
BEGIN
    -- Mark expired entries
    UPDATE cache_entries
    SET status = 'expired'
    WHERE expires_at IS NOT NULL
    AND expires_at <= CURRENT_TIMESTAMP
    AND status = 'valid';

    GET DIAGNOSTICS v_evicted_count = ROW_COUNT;

    -- Optionally delete old expired entries (older than 30 days)
    DELETE FROM cache_entries
    WHERE status = 'expired'
    AND expires_at < CURRENT_TIMESTAMP - INTERVAL '30 days';

    RETURN v_evicted_count;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION cleanup_old_logs(p_days INTEGER DEFAULT 90) RETURNS INTEGER AS $$
DECLARE
    v_deleted_count INTEGER;
BEGIN
    DELETE FROM cache_access_log
    WHERE timestamp < CURRENT_TIMESTAMP - (p_days || ' days')::INTERVAL;

    GET DIAGNOSTICS v_deleted_count = ROW_COUNT;

    RETURN v_deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Trigger to update cache stats
CREATE OR REPLACE FUNCTION update_cache_stats()
RETURNS TRIGGER AS $$
BEGIN
    -- Aggregate stats into hourly buckets
    INSERT INTO cache_stats (
        period_start,
        period_end,
        simulation_id,
        total_requests,
        cache_hits,
        cache_misses,
        hit_rate
    )
    SELECT
        date_trunc('hour', timestamp) as period_start,
        date_trunc('hour', timestamp) + INTERVAL '1 hour' as period_end,
        simulation_id,
        COUNT(*) as total_requests,
        SUM(CASE WHEN hit THEN 1 ELSE 0 END) as cache_hits,
        SUM(CASE WHEN NOT hit THEN 1 ELSE 0 END) as cache_misses,
        CASE
            WHEN COUNT(*) > 0 THEN
                100.0 * SUM(CASE WHEN hit THEN 1 ELSE 0 END) / COUNT(*)
            ELSE 0
        END as hit_rate
    FROM cache_access_log
    WHERE timestamp >= date_trunc('hour', CURRENT_TIMESTAMP - INTERVAL '1 hour')
    AND timestamp < date_trunc('hour', CURRENT_TIMESTAMP)
    GROUP BY date_trunc('hour', timestamp), simulation_id
    ON CONFLICT (period_start, period_end, simulation_id) DO UPDATE SET
        total_requests = EXCLUDED.total_requests,
        cache_hits = EXCLUDED.cache_hits,
        cache_misses = EXCLUDED.cache_misses,
        hit_rate = EXCLUDED.hit_rate;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
