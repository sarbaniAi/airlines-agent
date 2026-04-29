"""
Shared database connection for Pre-Flight Dispatch demo.
Uses Databricks SDK Statement Execution for reliable data access.
"""
import os
import re
import logging
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

logger = logging.getLogger("db")

CATALOG = "sarbanimaiti_catalog"
SCHEMA = "pre_flight_dispatch"
WAREHOUSE_ID = os.environ.get("DATABRICKS_WAREHOUSE_ID", "148ccb90800933a1")

TABLES = [
    "aircraft_fleet", "aircraft_certificates", "mel_items",
    "crew_roster", "flight_schedule", "weather_conditions",
    "regulatory_requirements",
]

_ws_client = None

def _get_ws():
    global _ws_client
    if _ws_client is None:
        _ws_client = WorkspaceClient()
    return _ws_client


def _qualify_tables(query):
    for table in TABLES:
        fqn = f"{CATALOG}.{SCHEMA}.{table}"
        query = re.sub(rf'\b{table}\b', fqn, query)
    return query


class _SDKCursor:
    def __init__(self, warehouse_id, return_dicts=False):
        self._wh = warehouse_id
        self._results = []
        self._columns = []
        self._return_dicts = return_dicts

    def execute(self, query, params=None):
        if params:
            processed = query
            for p in params:
                if isinstance(p, str):
                    processed = processed.replace("%s", f"'{p.replace(chr(39), chr(39)+chr(39))}'", 1)
                elif p is None:
                    processed = processed.replace("%s", "NULL", 1)
                else:
                    processed = processed.replace("%s", str(p), 1)
            query = processed

        query = _qualify_tables(query)

        w = _get_ws()
        response = w.statement_execution.execute_statement(
            warehouse_id=self._wh,
            statement=query,
            wait_timeout="30s",
            catalog=CATALOG,
            schema=SCHEMA,
        )

        if response.status and response.status.state == StatementState.FAILED:
            err = response.status.error.message if response.status.error else "Unknown"
            logger.error(f"SQL Error: {err}\nQuery: {query[:500]}")
            raise Exception(f"SQL Error: {err}")

        self._columns = []
        if response.manifest and response.manifest.schema and response.manifest.schema.columns:
            self._columns = [c.name for c in response.manifest.schema.columns]

        self._results = []
        if response.result and response.result.data_array:
            col_types = {}
            if response.manifest and response.manifest.schema and response.manifest.schema.columns:
                col_types = {c.name: c.type_text for c in response.manifest.schema.columns}

            for row in response.result.data_array:
                typed = []
                for i, val in enumerate(row):
                    if val is None:
                        typed.append(None)
                    elif i < len(self._columns) and col_types.get(self._columns[i], "") in ("INT", "BIGINT", "SMALLINT"):
                        try: typed.append(int(val))
                        except: typed.append(val)
                    elif i < len(self._columns) and col_types.get(self._columns[i], "") in ("DECIMAL", "FLOAT", "DOUBLE"):
                        try: typed.append(float(val))
                        except: typed.append(val)
                    elif i < len(self._columns) and col_types.get(self._columns[i], "") == "BOOLEAN":
                        typed.append(str(val).lower() == "true")
                    else:
                        typed.append(val)
                self._results.append(typed)

    def fetchall(self):
        if self._return_dicts:
            return [dict(zip(self._columns, row)) for row in self._results]
        return self._results

    def fetchone(self):
        if not self._results:
            return None
        if self._return_dicts:
            return dict(zip(self._columns, self._results[0]))
        return self._results[0]

    def close(self):
        pass


class _SDKConnection:
    def __init__(self):
        pass

    def cursor(self, cursor_factory=None):
        use_dicts = cursor_factory is not None and "Dict" in str(cursor_factory)
        return _SDKCursor(WAREHOUSE_ID, return_dicts=use_dicts)

    def close(self): pass
    def commit(self): pass
    def rollback(self): pass
    def set_isolation_level(self, level): pass

    @property
    def autocommit(self): return True
    @autocommit.setter
    def autocommit(self, val): pass


class RealDictCursor:
    pass


def get_db():
    return _SDKConnection()

def refresh_creds():
    global _ws_client
    _ws_client = None
