"""
Pre-Flight Dispatch V2 — Evaluation Dataset Loader.

Loads labeled evaluation scenarios from JSON files and provides
them in formats suitable for MLflow evaluation.
"""

import json
import logging
import os
from typing import Any

import pandas as pd

logger = logging.getLogger("evaluation.eval_dataset")

SCENARIOS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scenarios")

SCENARIO_FILES = {
    "go": os.path.join(SCENARIOS_DIR, "go_scenarios.json"),
    "nogo": os.path.join(SCENARIOS_DIR, "nogo_scenarios.json"),
    "conditional": os.path.join(SCENARIOS_DIR, "conditional_scenarios.json"),
}


def load_scenarios(category: str | None = None) -> list[dict[str, Any]]:
    """
    Load evaluation scenarios from JSON files.

    Args:
        category: Optional filter — "go", "nogo", "conditional", or None for all.

    Returns:
        List of scenario dictionaries.
    """
    scenarios: list[dict] = []

    files_to_load = (
        {category: SCENARIO_FILES[category]}
        if category and category in SCENARIO_FILES
        else SCENARIO_FILES
    )

    for cat, filepath in files_to_load.items():
        if not os.path.exists(filepath):
            logger.warning(f"Scenario file not found: {filepath}")
            continue
        with open(filepath, "r") as f:
            data = json.load(f)
            for scenario in data:
                scenario["category"] = cat
            scenarios.extend(data)

    logger.info(f"Loaded {len(scenarios)} evaluation scenarios")
    return scenarios


def scenarios_to_dataframe(scenarios: list[dict] | None = None) -> pd.DataFrame:
    """
    Convert scenarios to a pandas DataFrame suitable for MLflow evaluation.

    The DataFrame has columns:
        - scenario_id, description, flight_id, category
        - expected_decision, expected_risk
        - key_checks (JSON string)
        - expected_conditions (JSON string, if present)
        - expected_triggered_rules (JSON string, if present)

    Args:
        scenarios: Optional list of scenario dicts. If None, loads all.

    Returns:
        pd.DataFrame
    """
    if scenarios is None:
        scenarios = load_scenarios()

    rows = []
    for s in scenarios:
        rows.append({
            "scenario_id": s["scenario_id"],
            "description": s["description"],
            "flight_id": s["flight_id"],
            "category": s.get("category", "unknown"),
            "expected_decision": s["expected_decision"],
            "expected_risk": s.get("expected_risk", "UNKNOWN"),
            "key_checks": json.dumps(s.get("key_checks", [])),
            "expected_conditions": json.dumps(s.get("expected_conditions", [])),
            "expected_triggered_rules": json.dumps(s.get("expected_triggered_rules", [])),
        })

    return pd.DataFrame(rows)


def get_scenario_by_id(scenario_id: str) -> dict | None:
    """Look up a single scenario by its ID."""
    all_scenarios = load_scenarios()
    for s in all_scenarios:
        if s["scenario_id"] == scenario_id:
            return s
    return None


def get_scenario_count() -> dict[str, int]:
    """Return count of scenarios per category."""
    counts = {}
    for cat in SCENARIO_FILES:
        scenarios = load_scenarios(cat)
        counts[cat] = len(scenarios)
    counts["total"] = sum(counts.values())
    return counts


if __name__ == "__main__":
    # Quick sanity check
    counts = get_scenario_count()
    print(f"Evaluation scenarios loaded:")
    for cat, count in counts.items():
        print(f"  {cat}: {count}")

    df = scenarios_to_dataframe()
    print(f"\nDataFrame shape: {df.shape}")
    print(f"Columns: {list(df.columns)}")
    print(f"\nSample rows:")
    print(df[["scenario_id", "expected_decision", "expected_risk"]].head(10))
