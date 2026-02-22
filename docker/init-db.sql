-- Initialize PostgreSQL databases for sim2l services

-- Create separate databases for services and integration tests
CREATE DATABASE sim2l_cache;
CREATE DATABASE sim2l_catalog;
CREATE DATABASE sim2l_results;
CREATE DATABASE sim2l_test;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE sim2l_cache TO sim2l;
GRANT ALL PRIVILEGES ON DATABASE sim2l_catalog TO sim2l;
GRANT ALL PRIVILEGES ON DATABASE sim2l_results TO sim2l;
GRANT ALL PRIVILEGES ON DATABASE sim2l_test TO sim2l;
