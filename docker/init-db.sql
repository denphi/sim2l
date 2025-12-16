-- Initialize PostgreSQL databases for sim2l services

-- Create separate databases for cache and catalog
CREATE DATABASE sim2l_cache;
CREATE DATABASE sim2l_catalog;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE sim2l_cache TO sim2l;
GRANT ALL PRIVILEGES ON DATABASE sim2l_catalog TO sim2l;
