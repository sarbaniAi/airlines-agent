"""
Vector Search RAG tools — searches the regulatory_docs index for
DGCA CARs, Airworthiness Directives, and Dispatch SOPs.
"""

import logging
from typing import Optional

from databricks.sdk import WorkspaceClient

from config import VS_ENDPOINT, VS_INDEX

logger = logging.getLogger("tools.vector_search")

_ws: Optional[WorkspaceClient] = None


def _get_ws() -> WorkspaceClient:
    global _ws
    if _ws is None:
        _ws = WorkspaceClient()
    return _ws


def search_regulations(
    query: str,
    doc_type: Optional[str] = None,
    num_results: int = 5,
) -> list[dict]:
    """
    Search the regulatory documents Vector Search index.

    Args:
        query: Natural-language search query.
        doc_type: Optional filter — one of 'dgca_car', 'airworthiness_directive', 'dispatch_sop'.
                  If None, searches all document types.
        num_results: Number of results to return (default 5).

    Returns:
        List of dicts with keys: content, doc_type, doc_id, section, score.
        Returns empty list on failure (graceful degradation).
    """
    w = _get_ws()

    # Build filters
    filters = {}
    if doc_type:
        filters["doc_type"] = doc_type

    columns = ["content", "doc_type", "doc_id", "section", "title"]

    try:
        response = w.vector_search_indexes.query_index(
            index_name=VS_INDEX,
            query_text=query,
            columns=columns,
            num_results=num_results,
            filters_json=filters if filters else None,
        )

        results = []
        if response and response.result and response.result.data_array:
            col_names = [c.name for c in response.manifest.columns] if response.manifest and response.manifest.columns else columns + ["score"]
            for row in response.result.data_array:
                result = dict(zip(col_names, row))
                results.append(result)

        logger.info(
            "VS search: query=%s, doc_type=%s, results=%d",
            query[:80], doc_type, len(results),
        )
        return results

    except Exception as e:
        logger.warning("Vector Search query failed (graceful degradation): %s", e)
        return []


def search_airworthiness_directives(query: str, num_results: int = 5) -> list[dict]:
    """Search specifically for Airworthiness Directives."""
    return search_regulations(query, doc_type="airworthiness_directive", num_results=num_results)


def search_dgca_cars(query: str, num_results: int = 5) -> list[dict]:
    """Search specifically for DGCA Civil Aviation Requirements."""
    return search_regulations(query, doc_type="dgca_car", num_results=num_results)


def search_dispatch_sops(query: str, num_results: int = 5) -> list[dict]:
    """Search specifically for Dispatch SOPs."""
    return search_regulations(query, doc_type="dispatch_sop", num_results=num_results)


def test_vs_connectivity() -> bool:
    """Quick health check for Vector Search endpoint."""
    try:
        results = search_regulations("test connectivity", num_results=1)
        # Even empty results mean the endpoint is reachable
        return True
    except Exception as e:
        logger.warning("VS connectivity test failed: %s", e)
        return False
