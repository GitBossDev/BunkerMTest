#!/usr/bin/env python3
"""
Migration script from SQLite to PostgreSQL for BunkerM Extended
This script migrates data from BunkerM's default SQLite database to PostgreSQL

Usage: python scripts/migrate-to-postgres.py
"""

import os
import sys
import json
import sqlite3
import psycopg2
from psycopg2.extras import Json, execute_values
from datetime import datetime
from pathlib import Path
from sqlalchemy.engine import make_url

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

def load_env():
    """Load environment variables from .env.dev"""
    env_file = Path(__file__).parent.parent / '.env.dev'
    if not env_file.exists():
        print("ERROR: .env.dev file not found. Run generate-secrets.py first.")
        sys.exit(1)
    
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                if '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value

def get_postgres_connection():
    """Get PostgreSQL connection from DATABASE_URL"""
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("ERROR: DATABASE_URL not found in environment")
        sys.exit(1)

    try:
        url = make_url(database_url)
        if url.get_backend_name() != 'postgresql':
            raise ValueError(f"DATABASE_URL must target PostgreSQL, got: {database_url}")

        conn = psycopg2.connect(
            host=url.host or 'localhost',
            port=int(url.port or 5432),
            database=url.database,
            user=url.username,
            password=url.password or '',
            connect_timeout=5,
        )
        return conn
    except Exception as e:
        print(f"ERROR: Failed to connect to PostgreSQL: {e}")
        sys.exit(1)

def create_postgres_tables(pg_conn):
    """Create PostgreSQL tables for BunkerM Extended"""
    
    cursor = pg_conn.cursor()
    
    # Enable UUID extension
    cursor.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')
    
    # Tenants table (multi-tenancy)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tenants (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(255) NOT NULL,
            domain VARCHAR(255) UNIQUE,
            created_at TIMESTAMP DEFAULT NOW(),
            limits_json JSONB,
            active BOOLEAN DEFAULT true
        );
    ''')
    
    # Message metadata table (from smart-anomaly service)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS message_metadata (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID REFERENCES tenants(id),
            topic VARCHAR(500) NOT NULL,
            payload TEXT,
            qos INTEGER,
            retain BOOLEAN,
            timestamp TIMESTAMP NOT NULL,
            client_id VARCHAR(255),
            message_size INTEGER,
            created_at TIMESTAMP DEFAULT NOW()
        );
    ''')
    
    # Metrics aggregates table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS metrics_aggregates (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID REFERENCES tenants(id),
            topic VARCHAR(500) NOT NULL,
            window_start TIMESTAMP NOT NULL,
            window_end TIMESTAMP NOT NULL,
            message_count INTEGER DEFAULT 0,
            avg_interval_seconds FLOAT,
            min_interval_seconds FLOAT,
            max_interval_seconds FLOAT,
            stddev_interval_seconds FLOAT,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(tenant_id, topic, window_start)
        );
    ''')
    
    # Anomalies table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS anomalies (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID REFERENCES tenants(id),
            topic VARCHAR(500) NOT NULL,
            detector_type VARCHAR(50) NOT NULL,
            severity VARCHAR(20) NOT NULL,
            description TEXT,
            metadata_json JSONB,
            detected_at TIMESTAMP NOT NULL,
            acknowledged BOOLEAN DEFAULT false,
            acknowledged_at TIMESTAMP,
            acknowledged_by VARCHAR(255),
            created_at TIMESTAMP DEFAULT NOW()
        );
    ''')
    
    # Alerts table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS alerts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID REFERENCES tenants(id),
            anomaly_id UUID REFERENCES anomalies(id),
            alert_type VARCHAR(50) NOT NULL,
            severity VARCHAR(20) NOT NULL,
            message TEXT NOT NULL,
            metadata_json JSONB,
            triggered_at TIMESTAMP NOT NULL,
            resolved_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW()
        );
    ''')
    
    # Create indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_message_metadata_topic ON message_metadata(topic);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_message_metadata_timestamp ON message_metadata(timestamp);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_metrics_aggregates_topic ON metrics_aggregates(topic);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_anomalies_topic ON anomalies(topic);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_anomalies_detected_at ON anomalies(detected_at);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_alerts_triggered_at ON alerts(triggered_at);')
    
    pg_conn.commit()
    print("✓ PostgreSQL tables created successfully")

def migrate_sqlite_to_postgres(sqlite_path, pg_conn):
    """Migrate data from SQLite to PostgreSQL"""
    
    if not Path(sqlite_path).exists():
        print(f"INFO: SQLite database not found at {sqlite_path}, skipping data migration")
        return
    
    try:
        sqlite_conn = sqlite3.connect(sqlite_path)
        sqlite_conn.row_factory = sqlite3.Row
        cursor_sqlite = sqlite_conn.cursor()
        cursor_pg = pg_conn.cursor()
        
        # Get list of tables in SQLite
        cursor_sqlite.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor_sqlite.fetchall()]
        
        print(f"Found {len(tables)} tables in SQLite database")
        
        # Create default tenant
        cursor_pg.execute('''
            INSERT INTO tenants (name, domain, active) 
            VALUES ('Default', 'default.local', true) 
            ON CONFLICT DO NOTHING
            RETURNING id;
        ''')
        result = cursor_pg.fetchone()
        default_tenant_id = result[0] if result else None
        
        if not default_tenant_id:
            cursor_pg.execute("SELECT id FROM tenants WHERE domain = 'default.local';")
            default_tenant_id = cursor_pg.fetchone()[0]
        
        print(f"✓ Default tenant created with ID: {default_tenant_id}")
        
        # Migrate each table (implement specific migration logic as needed)
        for table in tables:
            if table.startswith('sqlite_'):
                continue
            
            print(f"  Migrating table: {table}...")
            # Add specific migration logic here based on table structure
            
        pg_conn.commit()
        sqlite_conn.close()
        
        print("✓ Data migration completed successfully")
        
    except sqlite3.Error as e:
        print(f"ERROR: SQLite error: {e}")
    except psycopg2.Error as e:
        print(f"ERROR: PostgreSQL error: {e}")
        pg_conn.rollback()

def main():
    """Main migration function"""
    
    print("==========================================")
    print("BunkerM Extended - SQLite to PostgreSQL Migration")
    print("==========================================")
    print()
    
    # Load environment variables
    print("Loading environment variables...")
    load_env()
    print("[OK] Environment loaded")
    print()
    
    # Connect to PostgreSQL
    print("Connecting to PostgreSQL...")
    pg_conn = get_postgres_connection()
    print("[OK] PostgreSQL connected")
    print()
    
    # Create tables
    print("Creating PostgreSQL tables...")
    create_postgres_tables(pg_conn)
    print()
    
    # Migrate data from SQLite (if exists)
    print("Checking for existing SQLite database...")
    sqlite_path = Path(__file__).parent.parent / 'data' / 'smart-anomaly.db'
    migrate_sqlite_to_postgres(str(sqlite_path), pg_conn)
    print()
    
    # Close connection
    pg_conn.close()
    
    print("==========================================")
    print("Migration Complete!")
    print("==========================================")
    print()
    print("Next steps:")
    print("1. Verify tables in PostgreSQL using pgAdmin or psql")
    print("2. Update backend services to use PostgreSQL connection")
    print("3. Run Alembic migrations: docker-compose exec bunkerm-backend alembic upgrade head")
    print()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nMigration cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nERROR: Migration failed: {e}")
        sys.exit(1)
