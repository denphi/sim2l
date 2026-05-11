-- @package    sim2l library
-- @copyright  Copyright (c) 2005-2026 Purdue University.
-- @license    http://opensource.org/licenses/MIT MIT

-- sim2l database schema

-- Simulations table: stores simulation definitions
CREATE TABLE IF NOT EXISTS simulations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    author TEXT,
    tags TEXT,  -- JSON array
    input_schema TEXT NOT NULL,  -- JSON
    output_schema TEXT NOT NULL,  -- JSON
    workflow_type TEXT NOT NULL,  -- 'notebook', 'function', 'dag'
    workflow_data BLOB NOT NULL,  -- Notebook bytes or function source bytes
    workflow_hash TEXT,
    dependencies TEXT,  -- JSON array
    status TEXT NOT NULL DEFAULT 'active',  -- 'active', 'deprecated', 'archived'
    UNIQUE(name, version)
);

CREATE INDEX IF NOT EXISTS idx_simulations_name ON simulations(name);
CREATE INDEX IF NOT EXISTS idx_simulations_status ON simulations(status);
CREATE INDEX IF NOT EXISTS idx_simulations_created_at ON simulations(created_at);

-- Executions table: stores execution history
CREATE TABLE IF NOT EXISTS executions (
    id TEXT PRIMARY KEY,  -- UUID
    simulation_id INTEGER NOT NULL,
    simulation_name TEXT NOT NULL,  -- Denormalized for easier queries
    simulation_version TEXT NOT NULL,  -- Denormalized
    executed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    duration_seconds REAL,
    executor_type TEXT NOT NULL,  -- 'local', 'notebook', 'submit'
    executor_config TEXT,  -- JSON
    inputs TEXT NOT NULL,  -- JSON serialized inputs
    status TEXT NOT NULL,  -- 'running', 'completed', 'failed', 'cached'
    error_message TEXT,
    cache_key TEXT,
    user TEXT,
    environment TEXT,  -- JSON (Python version, platform, etc.)
    FOREIGN KEY (simulation_id) REFERENCES simulations(id)
);

CREATE INDEX IF NOT EXISTS idx_executions_simulation_id ON executions(simulation_id);
CREATE INDEX IF NOT EXISTS idx_executions_executed_at ON executions(executed_at);
CREATE INDEX IF NOT EXISTS idx_executions_status ON executions(status);
CREATE INDEX IF NOT EXISTS idx_executions_cache_key ON executions(cache_key);

-- Outputs table: stores execution outputs
CREATE TABLE IF NOT EXISTS outputs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id TEXT NOT NULL,
    name TEXT NOT NULL,
    type TEXT NOT NULL,  -- Field type name
    value TEXT,  -- JSON serialized value (for small data)
    value_blob BLOB,  -- Binary data (for large arrays, pickled objects)
    file_path TEXT,  -- File reference for very large outputs
    units TEXT,  -- Physical units (if applicable)
    metadata TEXT,  -- JSON additional metadata
    FOREIGN KEY (execution_id) REFERENCES executions(id),
    UNIQUE(execution_id, name)
);

CREATE INDEX IF NOT EXISTS idx_outputs_execution_id ON outputs(execution_id);

-- Artifacts table: stores large binary artifacts
CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,  -- Content hash (SHA256)
    execution_id TEXT NOT NULL,
    name TEXT NOT NULL,
    content_type TEXT,  -- MIME type
    size_bytes INTEGER,
    storage_type TEXT NOT NULL,  -- 'blob', 'file', 's3'
    storage_path TEXT,  -- Path or URL
    data BLOB,  -- Actual data (if storage_type='blob')
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (execution_id) REFERENCES executions(id)
);

CREATE INDEX IF NOT EXISTS idx_artifacts_execution_id ON artifacts(execution_id);

-- Cache table: fast cache lookup
CREATE TABLE IF NOT EXISTS cache (
    cache_key TEXT PRIMARY KEY,
    execution_id TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_accessed TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    access_count INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (execution_id) REFERENCES executions(id)
);

-- Simulation tags table: many-to-many relationship
CREATE TABLE IF NOT EXISTS simulation_tags (
    simulation_id INTEGER NOT NULL,
    tag TEXT NOT NULL,
    FOREIGN KEY (simulation_id) REFERENCES simulations(id),
    PRIMARY KEY (simulation_id, tag)
);

CREATE INDEX IF NOT EXISTS idx_simulation_tags_tag ON simulation_tags(tag);
CREATE INDEX IF NOT EXISTS idx_simulation_tags_simulation_id ON simulation_tags(simulation_id);
