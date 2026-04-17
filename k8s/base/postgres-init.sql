-- ==========================================
-- BunkerM Extended - PostgreSQL Initialization
-- ==========================================
-- This script runs automatically when the PostgreSQL container starts for the first time

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

DO $$
BEGIN
    RAISE NOTICE 'BunkerM Extended PostgreSQL database initialized successfully';
END $$;