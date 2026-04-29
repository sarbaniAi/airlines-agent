"""
Seed Unstructured Data for Pre-Flight Dispatch V2
===================================================
Reads regulatory markdown documents, chunks them by section,
creates a Delta table, and sets up a Vector Search index.

Usage:
    Run from a Databricks notebook or local environment with
    Databricks SDK credentials configured (e.g., profile 'adb-984752964297111').

    python seed_unstructured.py
"""

import os
import re
import time
import hashlib
from pathlib import Path
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState
from databricks.sdk.service.catalog import (
    OnlineTableSpec,
    OnlineTableSpecTriggeredSchedulingPolicy,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CATALOG = "sarbanimaiti_catalog"
SCHEMA = "pre_flight_dispatch"
TABLE_NAME = "regulatory_docs"
FULL_TABLE_NAME = f"{CATALOG}.{SCHEMA}.{TABLE_NAME}"

VS_ENDPOINT = "one-env-shared-endpoint-11"
VS_INDEX_NAME = f"{CATALOG}.{SCHEMA}.{TABLE_NAME}_index"
EMBEDDING_MODEL = "databricks-gte-large-en"

# Path to the documents directory (relative to this script)
DOCS_DIR = Path(__file__).parent / "documents"

# SQL warehouse — will use serverless or first available warehouse
WAREHOUSE_ID = None  # Set explicitly if needed, otherwise auto-detected

# Chunking configuration
MAX_CHUNK_TOKENS = 500  # approximate tokens per chunk
CHARS_PER_TOKEN = 4     # rough estimate: 1 token ~ 4 characters
MAX_CHUNK_CHARS = MAX_CHUNK_TOKENS * CHARS_PER_TOKEN

# Document metadata mapping
DOC_METADATA = {
    "dgca_car_ops.md": {
        "source": "DGCA Civil Aviation Requirements",
        "doc_type": "regulation",
    },
    "airworthiness_directives.md": {
        "source": "DGCA Airworthiness Directives",
        "doc_type": "airworthiness_directive",
    },
    "dispatch_sops.md": {
        "source": "Air India Dispatch SOPs",
        "doc_type": "standard_operating_procedure",
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def generate_id(content: str, source: str, section: str) -> str:
    """Generate a deterministic ID from content + metadata."""
    raw = f"{source}::{section}::{content[:200]}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def chunk_markdown_by_section(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[dict]:
    """
    Split a markdown document into chunks based on headings.

    Strategy:
    - Split on ## and ### headings to get logical sections.
    - If a section exceeds max_chars, split further on paragraph boundaries.
    - Each chunk retains its section heading for context.
    """
    chunks = []

    # Split on level-2 and level-3 headings, keeping the heading with the content
    # Pattern: match lines starting with ## or ### (but not #### for granularity)
    sections = re.split(r'(?=^#{2,3}\s)', text, flags=re.MULTILINE)

    for section in sections:
        section = section.strip()
        if not section:
            continue

        # Extract the section heading
        heading_match = re.match(r'^(#{2,3}\s+.+?)$', section, re.MULTILINE)
        section_title = heading_match.group(1).strip().lstrip('#').strip() if heading_match else "Introduction"

        if len(section) <= max_chars:
            chunks.append({
                "section": section_title,
                "content": section,
            })
        else:
            # Split large sections on sub-headings (####) or paragraph breaks
            sub_parts = re.split(r'(?=^####\s)', section, flags=re.MULTILINE)
            if len(sub_parts) == 1:
                # No sub-headings; split on double newlines (paragraphs)
                sub_parts = section.split('\n\n')

            current_chunk = ""
            for part in sub_parts:
                part = part.strip()
                if not part:
                    continue
                if len(current_chunk) + len(part) + 2 <= max_chars:
                    current_chunk = current_chunk + "\n\n" + part if current_chunk else part
                else:
                    if current_chunk:
                        chunks.append({
                            "section": section_title,
                            "content": current_chunk,
                        })
                    current_chunk = part

            if current_chunk:
                chunks.append({
                    "section": section_title,
                    "content": current_chunk,
                })

    return chunks


def find_warehouse(w: WorkspaceClient) -> str:
    """Find an available SQL warehouse."""
    if WAREHOUSE_ID:
        return WAREHOUSE_ID

    warehouses = w.warehouses.list()
    for wh in warehouses:
        if wh.state and wh.state.value in ("RUNNING", "STARTING"):
            print(f"  Using warehouse: {wh.name} ({wh.id})")
            return wh.id

    # Try serverless — just pick the first warehouse
    for wh in w.warehouses.list():
        print(f"  Using warehouse: {wh.name} ({wh.id}) — may need to start")
        return wh.id

    raise RuntimeError("No SQL warehouse found. Please set WAREHOUSE_ID explicitly.")


def execute_sql(w: WorkspaceClient, warehouse_id: str, sql: str, timeout: int = 120) -> None:
    """Execute a SQL statement and wait for completion."""
    resp = w.statement_execution.execute_statement(
        warehouse_id=warehouse_id,
        statement=sql,
        wait_timeout="0s",  # async
    )

    statement_id = resp.statement_id
    print(f"  Statement {statement_id} submitted...")

    # Poll for completion
    start = time.time()
    while time.time() - start < timeout:
        status = w.statement_execution.get_statement(statement_id)
        state = status.status.state

        if state == StatementState.SUCCEEDED:
            print(f"  Statement succeeded.")
            return
        elif state in (StatementState.FAILED, StatementState.CANCELED, StatementState.CLOSED):
            error = status.status.error
            raise RuntimeError(f"SQL failed ({state}): {error}")

        time.sleep(2)

    raise TimeoutError(f"SQL statement did not complete within {timeout}s")


def escape_sql_string(s: str) -> str:
    """Escape single quotes for SQL insertion."""
    return s.replace("'", "''").replace("\\", "\\\\")


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("Pre-Flight Dispatch V2 — Seed Unstructured Data")
    print("=" * 60)

    # Initialize Databricks client
    print("\n[1/5] Connecting to Databricks workspace...")
    w = WorkspaceClient()
    print(f"  Connected to: {w.config.host}")

    # Find SQL warehouse
    print("\n[2/5] Finding SQL warehouse...")
    warehouse_id = find_warehouse(w)

    # Read and chunk documents
    print("\n[3/5] Reading and chunking documents...")
    all_chunks = []

    for filename, metadata in DOC_METADATA.items():
        filepath = DOCS_DIR / filename
        if not filepath.exists():
            print(f"  WARNING: {filepath} not found, skipping.")
            continue

        text = filepath.read_text(encoding="utf-8")
        chunks = chunk_markdown_by_section(text)

        for chunk in chunks:
            chunk_id = generate_id(chunk["content"], metadata["source"], chunk["section"])
            all_chunks.append({
                "id": chunk_id,
                "content": chunk["content"],
                "source": metadata["source"],
                "section": chunk["section"],
                "doc_type": metadata["doc_type"],
            })

        print(f"  {filename}: {len(chunks)} chunks")

    print(f"  Total chunks: {len(all_chunks)}")

    # Create Delta table and insert data
    print("\n[4/5] Creating Delta table and inserting data...")

    # Drop table if exists and recreate
    drop_sql = f"DROP TABLE IF EXISTS {FULL_TABLE_NAME}"
    execute_sql(w, warehouse_id, drop_sql)

    create_sql = f"""
    CREATE TABLE IF NOT EXISTS {FULL_TABLE_NAME} (
        id STRING NOT NULL,
        content STRING NOT NULL,
        source STRING NOT NULL,
        section STRING NOT NULL,
        doc_type STRING NOT NULL
    )
    USING DELTA
    TBLPROPERTIES (
        'delta.enableChangeDataFeed' = 'true'
    )
    COMMENT 'Regulatory documents for Pre-Flight Dispatch V2 Vector Search RAG'
    """
    execute_sql(w, warehouse_id, create_sql)
    print("  Table created.")

    # Insert data in batches (to avoid SQL statement size limits)
    BATCH_SIZE = 20
    for i in range(0, len(all_chunks), BATCH_SIZE):
        batch = all_chunks[i:i + BATCH_SIZE]
        values = []
        for chunk in batch:
            val = (
                f"('{escape_sql_string(chunk['id'])}', "
                f"'{escape_sql_string(chunk['content'])}', "
                f"'{escape_sql_string(chunk['source'])}', "
                f"'{escape_sql_string(chunk['section'])}', "
                f"'{escape_sql_string(chunk['doc_type'])}')"
            )
            values.append(val)

        insert_sql = f"""
        INSERT INTO {FULL_TABLE_NAME}
        VALUES {', '.join(values)}
        """
        execute_sql(w, warehouse_id, insert_sql)
        print(f"  Inserted batch {i // BATCH_SIZE + 1} ({len(batch)} rows)")

    print(f"  Total rows inserted: {len(all_chunks)}")

    # Create Vector Search index
    print("\n[5/5] Creating Vector Search index...")

    # Check if index already exists
    try:
        existing = w.vector_search_indexes.get_index(index_name=VS_INDEX_NAME)
        print(f"  Index {VS_INDEX_NAME} already exists. Deleting and recreating...")
        w.vector_search_indexes.delete_index(index_name=VS_INDEX_NAME)
        print("  Existing index deleted. Waiting 10s before recreation...")
        time.sleep(10)
    except Exception:
        print(f"  No existing index found. Creating new index...")

    # Create the Delta Sync vector search index
    w.vector_search_indexes.create_index(
        name=VS_INDEX_NAME,
        endpoint_name=VS_ENDPOINT,
        primary_key="id",
        index_type="DELTA_SYNC",
        delta_sync_index_spec={
            "source_table": FULL_TABLE_NAME,
            "pipeline_type": "TRIGGERED",
            "embedding_source_columns": [
                {
                    "name": "content",
                    "embedding_model_endpoint_name": EMBEDDING_MODEL,
                }
            ],
        },
    )

    print(f"  Vector Search index created: {VS_INDEX_NAME}")
    print(f"  Endpoint: {VS_ENDPOINT}")
    print(f"  Embedding model: {EMBEDDING_MODEL}")
    print(f"  Source table: {FULL_TABLE_NAME}")

    # Wait for initial sync
    print("\n  Waiting for initial index sync (this may take a few minutes)...")
    max_wait = 300  # 5 minutes max
    start = time.time()
    while time.time() - start < max_wait:
        try:
            idx = w.vector_search_indexes.get_index(index_name=VS_INDEX_NAME)
            status = idx.status
            if status and status.ready:
                print(f"  Index is READY!")
                break
            print(f"  Index status: syncing... ({int(time.time() - start)}s elapsed)")
        except Exception as e:
            print(f"  Checking status... ({e})")
        time.sleep(15)
    else:
        print(f"  Index creation initiated but not yet ready after {max_wait}s.")
        print(f"  The index will continue syncing in the background.")
        print(f"  Check status at: {w.config.host}/#/vector-search")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Delta table:       {FULL_TABLE_NAME}")
    print(f"  Total documents:   {len(all_chunks)} chunks from {len(DOC_METADATA)} source files")
    print(f"  Vector index:      {VS_INDEX_NAME}")
    print(f"  VS endpoint:       {VS_ENDPOINT}")
    print(f"  Embedding model:   {EMBEDDING_MODEL}")
    print(f"\nTo query the index:")
    print(f"""
    from databricks.sdk import WorkspaceClient
    w = WorkspaceClient()
    results = w.vector_search_indexes.query_index(
        index_name="{VS_INDEX_NAME}",
        columns=["id", "content", "source", "section", "doc_type"],
        query_text="What are the FDTL limits for two-crew operations?",
        num_results=5,
    )
    for doc in results.result.data_array:
        print(doc)
    """)


if __name__ == "__main__":
    main()
