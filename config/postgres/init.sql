-- ==========================================
-- BunkerM Extended - PostgreSQL Initialization
-- ==========================================
-- This script runs automatically when the PostgreSQL container starts for the first time

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create initial schema (tables will be created by Alembic migrations)
-- This file is a placeholder for any initial setup

-- Log successful initialization
DO $$
BEGIN
    RAISE NOTICE 'BunkerM Extended PostgreSQL database initialized successfully';
END $$;
