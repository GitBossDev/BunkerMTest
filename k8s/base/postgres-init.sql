-- ==========================================
-- Broker Health Manager - PostgreSQL Initialization
-- ==========================================
-- Este script se ejecuta automaticamente cuando el contenedor PostgreSQL arranca
-- por primera vez. Define los schemas de dominio y los usuarios de servicio.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ---------------------------------------------------------------------------
-- Schemas de dominio
-- Cada schema aísla las tablas de un bounded-context, permitiendo:
--   - Permisos independientes por servicio
--   - Migraciones Alembic aisladas (version_table por schema)
--   - Acceso compartido futuro: otros microservicios se conectan solo al schema
--     que les corresponde usando un usuario PostgreSQL de mínimos privilegios.
-- ---------------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS control_plane;
CREATE SCHEMA IF NOT EXISTS history;
CREATE SCHEMA IF NOT EXISTS reporting;
CREATE SCHEMA IF NOT EXISTS identity;

-- ---------------------------------------------------------------------------
-- Usuario de servicio para el control-plane (bhm-api, bhm-reconciler)
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'bhm_cp') THEN
        CREATE ROLE bhm_cp WITH LOGIN PASSWORD 'bhm_cp_replace_in_production';
    END IF;
END $$;

GRANT USAGE, CREATE ON SCHEMA control_plane TO bhm_cp;
ALTER DEFAULT PRIVILEGES IN SCHEMA control_plane
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO bhm_cp;

-- ---------------------------------------------------------------------------
-- Usuario de servicio para history / reporting
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'bhm_hist') THEN
        CREATE ROLE bhm_hist WITH LOGIN PASSWORD 'bhm_hist_replace_in_production';
    END IF;
END $$;

GRANT USAGE, CREATE ON SCHEMA history TO bhm_hist;
GRANT USAGE, CREATE ON SCHEMA reporting TO bhm_hist;
ALTER DEFAULT PRIVILEGES IN SCHEMA history
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO bhm_hist;
ALTER DEFAULT PRIVILEGES IN SCHEMA reporting
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO bhm_hist;

-- ---------------------------------------------------------------------------
-- Usuario de servicio para el schema de identidad (bhm-identity, futuro Keycloak)
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'bhm_id') THEN
        CREATE ROLE bhm_id WITH LOGIN PASSWORD 'bhm_id_replace_in_production';
    END IF;
END $$;

GRANT USAGE, CREATE ON SCHEMA identity TO bhm_id;
ALTER DEFAULT PRIVILEGES IN SCHEMA identity
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO bhm_id;

-- El usuario principal 'bhm' mantiene acceso completo para compatibilidad
-- con las migrations existentes y el runtime de desarrollo.
GRANT USAGE, CREATE ON SCHEMA control_plane TO bhm;
GRANT USAGE, CREATE ON SCHEMA history TO bhm;
GRANT USAGE, CREATE ON SCHEMA reporting TO bhm;
GRANT USAGE, CREATE ON SCHEMA identity TO bhm;

DO $$
BEGIN
    RAISE NOTICE 'Broker Health Manager - base de datos inicializada con schemas: control_plane, history, reporting, identity';
END $$;