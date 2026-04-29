"""
Pre-Flight Dispatch V2 — Central Configuration.
All constants, table names, and model references in one place.
"""

import os

# ── Unity Catalog ──────────────────────────────────────────────────────────
CATALOG = "sarbanimaiti_catalog"
SCHEMA = "pre_flight_dispatch"
WAREHOUSE_ID = os.environ.get("DATABRICKS_WAREHOUSE_ID", "148ccb90800933a1")

# Fully-qualified table helper
def fqn(table: str) -> str:
    """Return fully-qualified Unity Catalog table name."""
    return f"{CATALOG}.{SCHEMA}.{table}"

# ── Known tables (for auto-qualification in SQL) ──────────────────────────
TABLES = [
    "aircraft_fleet",
    "aircraft_certificates",
    "mel_items",
    "crew_roster",
    "flight_schedule",
    "weather_conditions",
    "regulatory_requirements",
]

# ── Vector Search ──────────────────────────────────────────────────────────
VS_ENDPOINT = "one-env-shared-endpoint-11"
VS_INDEX = f"{CATALOG}.{SCHEMA}.regulatory_docs_index"

# ── LLM / Embedding ───────────────────────────────────────────────────────
LLM_MODEL = "databricks-gpt-oss-120b"
EMBEDDING_MODEL = "databricks-gte-large-en"

# ── Genie Space (placeholder — set when created) ──────────────────────────
GENIE_SPACE_ID = os.environ.get("GENIE_SPACE_ID", "")

# ── MLflow ─────────────────────────────────────────────────────────────────
MLFLOW_EXPERIMENT = "/Users/sarbani.maiti@databricks.com/pre-flight-dispatch-v2"
