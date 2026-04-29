#!/usr/bin/env python3
"""
Seed script for Air India Pre-Flight Dispatch Lakebase database.
Connects to Lakebase PostgreSQL and runs seed_data.sql.

Usage:
    python data/seed.py

Environment variables (set by Databricks Apps or manually):
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DBNAME
"""

import os
import sys
import psycopg2


def get_connection():
    """Get Lakebase PostgreSQL connection."""
    conn = psycopg2.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=os.environ.get("POSTGRES_PORT", "5432"),
        dbname=os.environ.get("POSTGRES_DBNAME", "airlines-pre-flight"),
        user=os.environ.get("POSTGRES_USER", ""),
        password=os.environ.get("POSTGRES_PASSWORD", ""),
        sslmode=os.environ.get("POSTGRES_SSLMODE", "require"),
    )
    return conn


def seed_database():
    """Read and execute seed_data.sql against Lakebase."""
    sql_path = os.path.join(os.path.dirname(__file__), "seed_data.sql")

    if not os.path.exists(sql_path):
        print(f"ERROR: {sql_path} not found")
        sys.exit(1)

    with open(sql_path, "r") as f:
        sql = f.read()

    print("Connecting to Lakebase...")
    conn = get_connection()
    conn.autocommit = False

    try:
        cur = conn.cursor()
        print("Executing seed_data.sql...")
        cur.execute(sql)
        conn.commit()
        print("Seed data loaded successfully!")

        # Verify counts
        tables = [
            "aircraft_fleet",
            "aircraft_certificates",
            "mel_items",
            "crew_roster",
            "flight_schedule",
            "weather_conditions",
            "regulatory_requirements",
        ]
        print("\nTable row counts:")
        for table in tables:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = cur.fetchone()[0]
            print(f"  {table}: {count} rows")

        cur.close()
    except Exception as e:
        conn.rollback()
        print(f"ERROR: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    seed_database()
