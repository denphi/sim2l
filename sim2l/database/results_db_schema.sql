-- @package    sim2l library
-- @copyright  Copyright (c) 2005-2026 Purdue University.
-- @license    http://opensource.org/licenses/MIT MIT

-- Results Database Schema for sim2l
-- Stores introspected simulation results with searchable parameters
--
-- This schema supports:
-- - Parameter introspection (inputs and outputs)
-- - Type-aware storage (integer, number, string, boolean, array, file, etc.)
-- - Search by parameter values
-- - Simulation schema versioning
-- - Full-text search on descriptions

-- ============================================================================
-- TABLE: simulation_schemas
-- Stores the parameter schema for each simulation tool/version
-- ============================================================================

CREATE TABLE IF NOT EXISTS simulation_schemas (
    id SERIAL PRIMARY KEY,
    tool_name VARCHAR(255) NOT NULL,
    tool_version VARCHAR(50) NOT NULL,
    schema_data JSONB NOT NULL,  -- Full schema: {input: {...}, output: {...}}
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tool_name, tool_version)
);

CREATE INDEX IF NOT EXISTS idx_simulation_schemas_tool ON simulation_schemas(tool_name);
CREATE INDEX IF NOT EXISTS idx_simulation_schemas_version ON simulation_schemas(tool_name, tool_version);

COMMENT ON TABLE simulation_schemas IS 'Stores parameter schemas for simulation tools';
COMMENT ON COLUMN simulation_schemas.schema_data IS 'JSON schema with input/output parameter definitions';

-- ============================================================================
-- TABLE: execution_results
-- Stores actual execution results with parameter values
-- ============================================================================

CREATE TABLE IF NOT EXISTS execution_results (
    id SERIAL PRIMARY KEY,
    execution_id VARCHAR(255) NOT NULL UNIQUE,
    simulation_name VARCHAR(255) NOT NULL,
    simulation_version VARCHAR(50) NOT NULL,
    schema_id INTEGER REFERENCES simulation_schemas(id),
    squid_id VARCHAR(255),  -- Simulation Query Unique Identifier
    input_params JSONB NOT NULL,  -- Actual input parameter values
    output_params JSONB,  -- Actual output parameter values
    status VARCHAR(50) DEFAULT 'pending',  -- pending, running, completed, failed
    duration_seconds REAL,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    run_db_path VARCHAR(500),  -- Path to the run database file
    metadata JSONB  -- Additional execution metadata
);

CREATE INDEX IF NOT EXISTS idx_execution_results_exec_id ON execution_results(execution_id);
CREATE INDEX IF NOT EXISTS idx_execution_results_simulation ON execution_results(simulation_name, simulation_version);
CREATE INDEX IF NOT EXISTS idx_execution_results_squid ON execution_results(squid_id);
CREATE INDEX IF NOT EXISTS idx_execution_results_status ON execution_results(status);
CREATE INDEX IF NOT EXISTS idx_execution_results_schema ON execution_results(schema_id);

-- GIN indexes for JSONB parameter searching
CREATE INDEX IF NOT EXISTS idx_execution_results_input_params ON execution_results USING GIN (input_params);
CREATE INDEX IF NOT EXISTS idx_execution_results_output_params ON execution_results USING GIN (output_params);

COMMENT ON TABLE execution_results IS 'Stores execution results with searchable parameters';
COMMENT ON COLUMN execution_results.input_params IS 'JSON object with input parameter values';
COMMENT ON COLUMN execution_results.output_params IS 'JSON object with output parameter values';

-- ============================================================================
-- TABLE: parameter_definitions
-- Detailed parameter metadata extracted from schemas
-- ============================================================================

CREATE TABLE IF NOT EXISTS parameter_definitions (
    id SERIAL PRIMARY KEY,
    schema_id INTEGER REFERENCES simulation_schemas(id) ON DELETE CASCADE,
    param_name VARCHAR(255) NOT NULL,
    param_type VARCHAR(50) NOT NULL,  -- integer, number, string, boolean, array, file, etc.
    classification VARCHAR(50) NOT NULL,  -- input or output
    label VARCHAR(255),
    description TEXT,
    units VARCHAR(50),
    min_value REAL,
    max_value REAL,
    default_value JSONB,
    choices JSONB,  -- For Choice parameters
    metadata JSONB,  -- Additional parameter metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_parameter_definitions_schema ON parameter_definitions(schema_id);
CREATE INDEX IF NOT EXISTS idx_parameter_definitions_name ON parameter_definitions(param_name);
CREATE INDEX IF NOT EXISTS idx_parameter_definitions_type ON parameter_definitions(param_type);
CREATE INDEX IF NOT EXISTS idx_parameter_definitions_class ON parameter_definitions(classification);

-- Full-text search on descriptions
CREATE INDEX IF NOT EXISTS idx_parameter_definitions_desc_fts ON parameter_definitions USING GIN (to_tsvector('english', description));

COMMENT ON TABLE parameter_definitions IS 'Detailed metadata for simulation parameters';

-- ============================================================================
-- TABLE: result_errors
-- Tracks errors during result registration/introspection
-- ============================================================================

CREATE TABLE IF NOT EXISTS result_errors (
    id SERIAL PRIMARY KEY,
    execution_id VARCHAR(255),
    simulation_name VARCHAR(255) NOT NULL,
    simulation_version VARCHAR(50),
    error_type VARCHAR(100),
    error_message TEXT NOT NULL,
    stack_trace TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_result_errors_exec_id ON result_errors(execution_id);
CREATE INDEX IF NOT EXISTS idx_result_errors_simulation ON result_errors(simulation_name);

COMMENT ON TABLE result_errors IS 'Tracks errors during result registration';

-- ============================================================================
-- TABLE: result_search_cache
-- Caches common search queries for performance
-- ============================================================================

CREATE TABLE IF NOT EXISTS result_search_cache (
    id SERIAL PRIMARY KEY,
    query_hash VARCHAR(64) NOT NULL UNIQUE,  -- Hash of query parameters
    query_params JSONB NOT NULL,
    result_ids INTEGER[] NOT NULL,
    result_count INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    access_count INTEGER DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_result_search_cache_hash ON result_search_cache(query_hash);
CREATE INDEX IF NOT EXISTS idx_result_search_cache_accessed ON result_search_cache(accessed_at);

COMMENT ON TABLE result_search_cache IS 'Caches search results for performance';

-- ============================================================================
-- VIEWS
-- ============================================================================

-- View: full_execution_results
-- Joins execution results with schema information
CREATE OR REPLACE VIEW full_execution_results AS
SELECT
    er.id,
    er.execution_id,
    er.simulation_name,
    er.simulation_version,
    er.squid_id,
    er.input_params,
    er.output_params,
    er.status,
    er.duration_seconds,
    er.error_message,
    er.created_at,
    er.completed_at,
    er.run_db_path,
    er.metadata,
    ss.schema_data
FROM execution_results er
LEFT JOIN simulation_schemas ss ON er.schema_id = ss.id;

COMMENT ON VIEW full_execution_results IS 'Execution results with schema information';

-- ============================================================================
-- FUNCTIONS
-- ============================================================================

-- Function: register_simulation_schema
-- Registers or updates a simulation schema
CREATE OR REPLACE FUNCTION register_simulation_schema(
    p_tool_name VARCHAR(255),
    p_tool_version VARCHAR(50),
    p_schema_data JSONB
) RETURNS INTEGER AS $$
DECLARE
    v_schema_id INTEGER;
BEGIN
    INSERT INTO simulation_schemas (tool_name, tool_version, schema_data, updated_at)
    VALUES (p_tool_name, p_tool_version, p_schema_data, CURRENT_TIMESTAMP)
    ON CONFLICT (tool_name, tool_version)
    DO UPDATE SET
        schema_data = EXCLUDED.schema_data,
        updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO v_schema_id;

    RETURN v_schema_id;
END;
$$ LANGUAGE plpgsql;

-- Function: register_execution_result
-- Registers an execution result with parameters
CREATE OR REPLACE FUNCTION register_execution_result(
    p_execution_id VARCHAR(255),
    p_simulation_name VARCHAR(255),
    p_simulation_version VARCHAR(50),
    p_squid_id VARCHAR(255),
    p_input_params JSONB,
    p_output_params JSONB,
    p_status VARCHAR(50),
    p_duration_seconds REAL,
    p_run_db_path VARCHAR(500),
    p_metadata JSONB
) RETURNS INTEGER AS $$
DECLARE
    v_schema_id INTEGER;
    v_result_id INTEGER;
BEGIN
    -- Get or create schema
    SELECT id INTO v_schema_id
    FROM simulation_schemas
    WHERE tool_name = p_simulation_name AND tool_version = p_simulation_version;

    -- Insert execution result
    INSERT INTO execution_results (
        execution_id, simulation_name, simulation_version, schema_id,
        squid_id, input_params, output_params, status, duration_seconds,
        run_db_path, metadata, completed_at
    ) VALUES (
        p_execution_id, p_simulation_name, p_simulation_version, v_schema_id,
        p_squid_id, p_input_params, p_output_params, p_status, p_duration_seconds,
        p_run_db_path, p_metadata, CURRENT_TIMESTAMP
    )
    ON CONFLICT (execution_id)
    DO UPDATE SET
        output_params = EXCLUDED.output_params,
        status = EXCLUDED.status,
        duration_seconds = EXCLUDED.duration_seconds,
        completed_at = CURRENT_TIMESTAMP
    RETURNING id INTO v_result_id;

    -- Invalidate search cache
    DELETE FROM result_search_cache WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '1 hour';

    RETURN v_result_id;
END;
$$ LANGUAGE plpgsql;

-- Function: search_results_by_params
-- Search execution results by parameter values
-- Helper function to check if a JSONB value matches a filter with operators
CREATE OR REPLACE FUNCTION matches_jsonb_filter(
    params JSONB,
    filters JSONB
) RETURNS BOOLEAN AS $$
DECLARE
    filter_key TEXT;
    filter_value JSONB;
    param_value JSONB;
    operator_key TEXT;
    operator_value JSONB;
BEGIN
    -- If filters is empty, match all
    IF filters = '{}'::JSONB THEN
        RETURN TRUE;
    END IF;

    -- Check each filter
    FOR filter_key, filter_value IN SELECT * FROM jsonb_each(filters) LOOP
        param_value := params -> filter_key;

        -- If parameter doesn't exist, no match
        IF param_value IS NULL THEN
            RETURN FALSE;
        END IF;

        -- Check if filter_value is an operator object (e.g., {"$gt": 100})
        IF jsonb_typeof(filter_value) = 'object' THEN
            -- Handle comparison operators
            FOR operator_key, operator_value IN SELECT * FROM jsonb_each(filter_value) LOOP
                IF operator_key = '$gt' THEN
                    IF NOT ((param_value)::numeric > (operator_value)::numeric) THEN
                        RETURN FALSE;
                    END IF;
                ELSIF operator_key = '$gte' THEN
                    IF NOT ((param_value)::numeric >= (operator_value)::numeric) THEN
                        RETURN FALSE;
                    END IF;
                ELSIF operator_key = '$lt' THEN
                    IF NOT ((param_value)::numeric < (operator_value)::numeric) THEN
                        RETURN FALSE;
                    END IF;
                ELSIF operator_key = '$lte' THEN
                    IF NOT ((param_value)::numeric <= (operator_value)::numeric) THEN
                        RETURN FALSE;
                    END IF;
                ELSIF operator_key = '$eq' THEN
                    IF param_value != operator_value THEN
                        RETURN FALSE;
                    END IF;
                END IF;
            END LOOP;
        ELSE
            -- Simple equality check
            IF param_value != filter_value THEN
                RETURN FALSE;
            END IF;
        END IF;
    END LOOP;

    RETURN TRUE;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

CREATE OR REPLACE FUNCTION search_results_by_params(
    p_simulation_name VARCHAR(255) DEFAULT NULL,
    p_simulation_version VARCHAR(50) DEFAULT NULL,
    p_status VARCHAR(50) DEFAULT NULL,
    p_input_filters JSONB DEFAULT '{}'::JSONB,
    p_output_filters JSONB DEFAULT '{}'::JSONB,
    p_limit INTEGER DEFAULT 100
) RETURNS TABLE (
    execution_id VARCHAR(255),
    simulation_name VARCHAR(255),
    simulation_version VARCHAR(50),
    squid_id VARCHAR(255),
    input_params JSONB,
    output_params JSONB,
    status VARCHAR(50),
    created_at TIMESTAMP
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        er.execution_id,
        er.simulation_name,
        er.simulation_version,
        er.squid_id,
        er.input_params,
        er.output_params,
        er.status,
        er.created_at
    FROM execution_results er
    WHERE
        (p_simulation_name IS NULL OR er.simulation_name = p_simulation_name)
        AND (p_simulation_version IS NULL OR er.simulation_version = p_simulation_version)
        AND (p_status IS NULL OR er.status = p_status)
        AND matches_jsonb_filter(er.input_params, p_input_filters)
        AND matches_jsonb_filter(er.output_params, p_output_filters)
    ORDER BY er.created_at DESC
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;

-- Function: get_parameter_statistics
-- Get statistics for a specific parameter across executions
CREATE OR REPLACE FUNCTION get_parameter_statistics(
    p_simulation_name VARCHAR(255),
    p_param_name VARCHAR(255),
    p_param_class VARCHAR(50) DEFAULT 'output'  -- 'input' or 'output'
) RETURNS TABLE (
    param_name VARCHAR(255),
    param_type VARCHAR(50),
    min_value NUMERIC,
    max_value NUMERIC,
    avg_value NUMERIC,
    count BIGINT
) AS $$
DECLARE
    v_param_column TEXT;
BEGIN
    -- Determine which column to query
    v_param_column := CASE WHEN p_param_class = 'input' THEN 'input_params' ELSE 'output_params' END;

    RETURN QUERY EXECUTE format('
        SELECT
            %L::VARCHAR(255) as param_name,
            ''number''::VARCHAR(50) as param_type,
            MIN((%s->>%L)::NUMERIC) as min_value,
            MAX((%s->>%L)::NUMERIC) as max_value,
            AVG((%s->>%L)::NUMERIC) as avg_value,
            COUNT(*) as count
        FROM execution_results
        WHERE simulation_name = %L
          AND %s ? %L
          AND %s->>%L ~ ''^[0-9.eE+-]+$''
    ', p_param_name, v_param_column, p_param_name, v_param_column, p_param_name,
       v_param_column, p_param_name, p_simulation_name, v_param_column, p_param_name,
       v_param_column, p_param_name);
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- TRIGGERS
-- ============================================================================

-- Trigger: update_schema_timestamp
CREATE OR REPLACE FUNCTION update_schema_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_schema_timestamp
BEFORE UPDATE ON simulation_schemas
FOR EACH ROW
EXECUTE FUNCTION update_schema_timestamp();

-- ============================================================================
-- INITIAL DATA
-- ============================================================================

-- Create default entries (none needed)

COMMENT ON SCHEMA public IS 'Sim2l Results Database - Stores introspected simulation results with searchable parameters';
