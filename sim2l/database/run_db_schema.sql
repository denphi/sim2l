-- Per-Run SQLite Database Schema
-- One database per execution run, stores complete run information

-- Metadata about this run
CREATE TABLE run_metadata (
    execution_id TEXT PRIMARY KEY,
    squid_id TEXT NOT NULL,
    simulation_name TEXT NOT NULL,
    simulation_version TEXT NOT NULL,
    simulation_id INTEGER,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    duration_seconds REAL,
    status TEXT NOT NULL, -- 'running', 'completed', 'failed', 'cached'
    executor_type TEXT NOT NULL,
    executor_config TEXT, -- JSON
    cache_key TEXT,
    cache_hit BOOLEAN DEFAULT 0,
    user_id TEXT,
    session_id TEXT,
    environment TEXT, -- JSON: python version, platform, packages, etc.
    error_message TEXT,
    error_traceback TEXT,
    notes TEXT
);

-- Input parameters for this run
CREATE TABLE inputs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL,
    value TEXT, -- JSON serialized
    value_blob BLOB, -- For large binary data
    units TEXT,
    metadata TEXT -- JSON
);

-- Output results from this run
CREATE TABLE outputs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL,
    value TEXT, -- JSON serialized
    value_blob BLOB, -- For large binary data
    units TEXT,
    file_reference TEXT, -- Reference to artifact if stored as file
    metadata TEXT, -- JSON
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Files and artifacts produced during run
CREATE TABLE artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    path TEXT, -- Relative path within run directory
    content_hash TEXT, -- SHA256 for deduplication
    content_type TEXT, -- MIME type
    size_bytes INTEGER,
    category TEXT, -- 'input', 'output', 'intermediate', 'notebook', 'plot', 'data'
    data BLOB, -- Actual file data (optional, can be external)
    external_path TEXT, -- Path to file outside database
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Execution logs (structured)
CREATE TABLE logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    level TEXT NOT NULL, -- 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'
    logger TEXT, -- Logger name (e.g., 'sim2l.executor', 'notebook.cell_5')
    message TEXT NOT NULL,
    context TEXT, -- JSON: cell number, function name, line number, etc.
    exception_type TEXT,
    exception_message TEXT,
    stack_trace TEXT
);

-- Cell execution tracking (for notebook runs)
CREATE TABLE cell_executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cell_index INTEGER NOT NULL,
    cell_type TEXT, -- 'code', 'markdown'
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    duration_seconds REAL,
    status TEXT, -- 'pending', 'running', 'completed', 'failed', 'skipped'
    source_code TEXT, -- Cell source code
    output_text TEXT, -- Cell output (stdout/stderr)
    output_data TEXT, -- JSON: display data, plots, etc.
    error_message TEXT,
    error_traceback TEXT
);

-- Performance metrics
CREATE TABLE metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL,
    metric_unit TEXT,
    category TEXT, -- 'performance', 'resource', 'custom'
    metadata TEXT -- JSON
);

-- Resource usage tracking
CREATE TABLE resource_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    cpu_percent REAL,
    memory_mb REAL,
    memory_percent REAL,
    disk_read_mb REAL,
    disk_write_mb REAL,
    network_sent_mb REAL,
    network_recv_mb REAL
);

-- Provenance and lineage
CREATE TABLE provenance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL, -- 'input', 'output', 'artifact', 'intermediate'
    entity_name TEXT NOT NULL,
    source_type TEXT, -- 'user_provided', 'computed', 'cached', 'derived_from'
    source_reference TEXT, -- Reference to source entity
    transformation TEXT, -- Description of how entity was created
    metadata TEXT -- JSON
);

-- Tags for categorization
CREATE TABLE tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tag TEXT NOT NULL UNIQUE
);

-- Many-to-many relationship for tags
CREATE TABLE run_tags (
    tag_id INTEGER NOT NULL,
    FOREIGN KEY (tag_id) REFERENCES tags(id),
    PRIMARY KEY (tag_id)
);

-- Checkpoints for long-running simulations
CREATE TABLE checkpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    checkpoint_name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    state_data TEXT, -- JSON serialized state
    state_blob BLOB, -- Binary state (pickled)
    description TEXT,
    is_final BOOLEAN DEFAULT 0
);

-- Indexes for common queries
CREATE INDEX idx_logs_timestamp ON logs(timestamp);
CREATE INDEX idx_logs_level ON logs(level);
CREATE INDEX idx_artifacts_category ON artifacts(category);
CREATE INDEX idx_artifacts_hash ON artifacts(content_hash);
CREATE INDEX idx_cell_executions_status ON cell_executions(status);
CREATE INDEX idx_metrics_name ON metrics(metric_name);
CREATE INDEX idx_provenance_entity ON provenance(entity_type, entity_name);

-- Views for common queries
CREATE VIEW run_summary AS
SELECT
    rm.execution_id,
    rm.squid_id,
    rm.simulation_name,
    rm.simulation_version,
    rm.started_at,
    rm.completed_at,
    rm.duration_seconds,
    rm.status,
    rm.cache_hit,
    COUNT(DISTINCT i.name) as input_count,
    COUNT(DISTINCT o.name) as output_count,
    COUNT(DISTINCT a.id) as artifact_count,
    COUNT(DISTINCT l.id) as log_count,
    SUM(CASE WHEN l.level = 'ERROR' THEN 1 ELSE 0 END) as error_count,
    SUM(CASE WHEN l.level = 'WARNING' THEN 1 ELSE 0 END) as warning_count
FROM run_metadata rm
LEFT JOIN inputs i ON 1=1
LEFT JOIN outputs o ON 1=1
LEFT JOIN artifacts a ON 1=1
LEFT JOIN logs l ON 1=1
GROUP BY rm.execution_id;

CREATE VIEW error_summary AS
SELECT
    timestamp,
    logger,
    message,
    exception_type,
    exception_message
FROM logs
WHERE level IN ('ERROR', 'CRITICAL')
ORDER BY timestamp DESC;
