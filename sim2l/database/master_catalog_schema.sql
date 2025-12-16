-- Master Catalog Database Schema (PostgreSQL)
-- Central registry for all sim2l tools, versions, and metadata

-- Users and authentication
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    email TEXT,
    full_name TEXT,
    organization TEXT,
    role TEXT NOT NULL DEFAULT 'user', -- 'admin', 'developer', 'user'
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP,
    metadata JSONB
);

-- Session management
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ip_address TEXT,
    user_agent TEXT,
    is_valid BOOLEAN DEFAULT true,
    privileges JSONB, -- Array of privileges: ['read', 'write', 'admin']
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Simulation registry (master list of all tools)
CREATE TABLE IF NOT EXISTS simulations (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    description TEXT,
    author TEXT,
    author_email TEXT,
    organization TEXT,
    license TEXT,
    repository_url TEXT,
    documentation_url TEXT,
    tags JSONB, -- Array of tags
    input_schema JSONB NOT NULL,
    output_schema JSONB NOT NULL,
    workflow_type TEXT NOT NULL, -- 'notebook', 'function', 'dag'
    workflow_hash TEXT NOT NULL, -- SHA256 for version verification
    dependencies JSONB, -- Array of package dependencies
    python_version TEXT, -- Minimum Python version required
    status TEXT NOT NULL DEFAULT 'active', -- 'active', 'deprecated', 'archived'
    visibility TEXT NOT NULL DEFAULT 'public', -- 'public', 'private', 'internal'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER,
    updated_by INTEGER,
    metadata JSONB,
    UNIQUE(name, version),
    FOREIGN KEY (created_by) REFERENCES users(id),
    FOREIGN KEY (updated_by) REFERENCES users(id)
);

-- Execution statistics (aggregated from runs)
CREATE TABLE IF NOT EXISTS execution_stats (
    id SERIAL PRIMARY KEY,
    simulation_id INTEGER NOT NULL,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    total_executions INTEGER DEFAULT 0,
    successful_executions INTEGER DEFAULT 0,
    failed_executions INTEGER DEFAULT 0,
    cached_executions INTEGER DEFAULT 0,
    total_duration_seconds REAL DEFAULT 0,
    avg_duration_seconds REAL DEFAULT 0,
    min_duration_seconds REAL,
    max_duration_seconds REAL,
    unique_users INTEGER DEFAULT 0,
    total_cache_hits INTEGER DEFAULT 0,
    cache_hit_rate REAL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(simulation_id, period_start),
    FOREIGN KEY (simulation_id) REFERENCES simulations(id) ON DELETE CASCADE
);

-- Execution registry (lightweight references to all runs)
CREATE TABLE IF NOT EXISTS execution_registry (
    id SERIAL PRIMARY KEY,
    execution_id TEXT NOT NULL UNIQUE,
    squid_id TEXT NOT NULL,
    simulation_id INTEGER NOT NULL,
    user_id INTEGER,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    duration_seconds REAL,
    status TEXT NOT NULL,
    executor_type TEXT NOT NULL,
    cache_hit BOOLEAN DEFAULT false,
    run_db_path TEXT, -- Path to per-run SQLite database
    run_db_size_bytes BIGINT,
    input_hash TEXT, -- Hash of inputs for quick matching
    output_count INTEGER DEFAULT 0,
    artifact_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    warning_count INTEGER DEFAULT 0,
    environment JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (simulation_id) REFERENCES simulations(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Client installations (track where sim2l is installed)
CREATE TABLE IF NOT EXISTS installations (
    id SERIAL PRIMARY KEY,
    installation_id TEXT NOT NULL UNIQUE,
    hostname TEXT,
    platform TEXT, -- 'linux', 'darwin', 'windows'
    python_version TEXT,
    sim2l_version TEXT,
    user_id INTEGER,
    last_sync TIMESTAMP,
    last_heartbeat TIMESTAMP,
    is_active BOOLEAN DEFAULT true,
    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Sync queue (pending updates from installations)
CREATE TABLE IF NOT EXISTS sync_queue (
    id SERIAL PRIMARY KEY,
    installation_id TEXT NOT NULL,
    operation TEXT NOT NULL, -- 'register', 'update', 'deprecate'
    simulation_name TEXT NOT NULL,
    simulation_version TEXT NOT NULL,
    payload JSONB NOT NULL, -- Full simulation metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP,
    status TEXT DEFAULT 'pending', -- 'pending', 'approved', 'rejected', 'failed'
    processed_by INTEGER,
    rejection_reason TEXT,
    FOREIGN KEY (installation_id) REFERENCES installations(installation_id),
    FOREIGN KEY (processed_by) REFERENCES users(id)
);

-- Tags for simulations
CREATE TABLE IF NOT EXISTS simulation_tags (
    simulation_id INTEGER NOT NULL,
    tag TEXT NOT NULL,
    FOREIGN KEY (simulation_id) REFERENCES simulations(id) ON DELETE CASCADE,
    PRIMARY KEY (simulation_id, tag)
);

-- Simulation dependencies graph
CREATE TABLE IF NOT EXISTS simulation_dependencies (
    id SERIAL PRIMARY KEY,
    simulation_id INTEGER NOT NULL,
    depends_on_simulation_id INTEGER NOT NULL,
    dependency_type TEXT, -- 'input', 'output', 'workflow'
    metadata JSONB,
    FOREIGN KEY (simulation_id) REFERENCES simulations(id) ON DELETE CASCADE,
    FOREIGN KEY (depends_on_simulation_id) REFERENCES simulations(id) ON DELETE CASCADE,
    UNIQUE(simulation_id, depends_on_simulation_id, dependency_type)
);

-- Access control (who can modify what)
CREATE TABLE IF NOT EXISTS access_control (
    id SERIAL PRIMARY KEY,
    simulation_id INTEGER NOT NULL,
    user_id INTEGER,
    role_name TEXT, -- 'owner', 'maintainer', 'contributor', 'viewer'
    granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    granted_by INTEGER,
    FOREIGN KEY (simulation_id) REFERENCES simulations(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (granted_by) REFERENCES users(id),
    UNIQUE(simulation_id, user_id)
);

-- Audit log for all catalog changes
CREATE TABLE IF NOT EXISTS audit_log (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_id INTEGER,
    session_id TEXT,
    action TEXT NOT NULL, -- 'create', 'update', 'delete', 'deprecate'
    entity_type TEXT NOT NULL, -- 'simulation', 'user', 'session', 'stats'
    entity_id INTEGER,
    changes JSONB, -- Before/after values
    ip_address TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Popular searches and queries
CREATE TABLE IF NOT EXISTS search_analytics (
    id SERIAL PRIMARY KEY,
    search_query TEXT NOT NULL,
    search_filters JSONB,
    result_count INTEGER,
    user_id INTEGER,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_simulations_name ON simulations(name);
CREATE INDEX IF NOT EXISTS idx_simulations_status ON simulations(status);
CREATE INDEX IF NOT EXISTS idx_simulations_tags ON simulations USING GIN(tags);
CREATE INDEX IF NOT EXISTS idx_simulations_created_at ON simulations(created_at);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_execution_registry_simulation ON execution_registry(simulation_id);
CREATE INDEX IF NOT EXISTS idx_execution_registry_user ON execution_registry(user_id);
CREATE INDEX IF NOT EXISTS idx_execution_registry_squid ON execution_registry(squid_id);
CREATE INDEX IF NOT EXISTS idx_execution_registry_started ON execution_registry(started_at);
CREATE INDEX IF NOT EXISTS idx_sync_queue_status ON sync_queue(status);
CREATE INDEX IF NOT EXISTS idx_sync_queue_installation ON sync_queue(installation_id);
CREATE INDEX IF NOT EXISTS idx_installations_active ON installations(is_active);
CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_log_user ON audit_log(user_id);

-- Views for common queries
CREATE OR REPLACE VIEW simulation_catalog AS
SELECT
    s.id,
    s.name,
    s.version,
    s.description,
    s.author,
    s.tags,
    s.status,
    s.visibility,
    s.created_at,
    s.updated_at,
    COALESCE(es.total_executions, 0) as total_executions,
    COALESCE(es.cache_hit_rate, 0) as cache_hit_rate,
    COALESCE(es.avg_duration_seconds, 0) as avg_duration_seconds,
    u.username as created_by_username
FROM simulations s
LEFT JOIN users u ON s.created_by = u.id
LEFT JOIN (
    SELECT
        simulation_id,
        SUM(total_executions) as total_executions,
        AVG(cache_hit_rate) as cache_hit_rate,
        AVG(avg_duration_seconds) as avg_duration_seconds
    FROM execution_stats
    WHERE period_start >= CURRENT_DATE - INTERVAL '90 days'
    GROUP BY simulation_id
) es ON s.id = es.simulation_id;

CREATE OR REPLACE VIEW active_sessions AS
SELECT
    s.session_id,
    s.user_id,
    u.username,
    u.role,
    s.created_at,
    s.expires_at,
    s.last_activity,
    s.privileges
FROM sessions s
JOIN users u ON s.user_id = u.id
WHERE s.is_valid = true
AND s.expires_at > CURRENT_TIMESTAMP;

CREATE OR REPLACE VIEW pending_sync_requests AS
SELECT
    sq.id,
    sq.installation_id,
    sq.operation,
    sq.simulation_name,
    sq.simulation_version,
    sq.created_at,
    i.hostname,
    i.user_id,
    u.username
FROM sync_queue sq
JOIN installations i ON sq.installation_id = i.installation_id
LEFT JOIN users u ON i.user_id = u.id
WHERE sq.status = 'pending'
ORDER BY sq.created_at;

-- Functions for privilege checking
CREATE OR REPLACE FUNCTION check_session_privilege(
    p_session_id TEXT,
    p_required_privilege TEXT
) RETURNS BOOLEAN AS $$
DECLARE
    v_has_privilege BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1
        FROM sessions
        WHERE session_id = p_session_id
        AND is_valid = true
        AND expires_at > CURRENT_TIMESTAMP
        AND (
            privileges ? p_required_privilege
            OR privileges ? 'admin'
        )
    ) INTO v_has_privilege;

    -- Update last activity
    UPDATE sessions
    SET last_activity = CURRENT_TIMESTAMP
    WHERE session_id = p_session_id;

    RETURN v_has_privilege;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION check_simulation_access(
    p_session_id TEXT,
    p_simulation_id INTEGER,
    p_required_role TEXT
) RETURNS BOOLEAN AS $$
DECLARE
    v_user_id INTEGER;
    v_has_access BOOLEAN;
BEGIN
    -- Get user from session
    SELECT user_id INTO v_user_id
    FROM sessions
    WHERE session_id = p_session_id
    AND is_valid = true
    AND expires_at > CURRENT_TIMESTAMP;

    IF v_user_id IS NULL THEN
        RETURN false;
    END IF;

    -- Check if user is admin
    IF EXISTS (
        SELECT 1 FROM users WHERE id = v_user_id AND role = 'admin'
    ) THEN
        RETURN true;
    END IF;

    -- Check access control
    SELECT EXISTS (
        SELECT 1
        FROM access_control
        WHERE simulation_id = p_simulation_id
        AND user_id = v_user_id
        AND role_name IN ('owner', 'maintainer', 'contributor')
    ) INTO v_has_access;

    RETURN v_has_access;
END;
$$ LANGUAGE plpgsql;

-- Trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_simulations_updated_at
    BEFORE UPDATE ON simulations
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
