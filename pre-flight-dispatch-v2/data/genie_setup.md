# Genie Space Setup — Air India Flight Ops Intelligence

## Overview
This document provides instructions for creating the Genie Space for the Pre-Flight Dispatch V2 system. The Genie Space enables natural language queries against the structured flight operations tables, powering the Genie Agent in the multi-agent system.

Since Genie Space creation requires UI interaction, follow these manual steps in the Databricks workspace.

---

## Step 1: Create the Genie Space

1. Navigate to the Databricks workspace: https://adb-984752964297111.11.azuredatabricks.net/
2. In the left sidebar, click **Genie** (under the "AI/BI" section).
3. Click **New** to create a new Genie Space.
4. Set the space name to: **Air India Flight Ops Intelligence**
5. Optionally add a description: "Natural language interface for flight operations data including fleet status, crew rostering, weather, maintenance, and regulatory compliance."

## Step 2: Add Tables

Add the following 7 tables from `sarbanimaiti_catalog.pre_flight_dispatch`:

| # | Table Name | Description |
|---|---|---|
| 1 | `sarbanimaiti_catalog.pre_flight_dispatch.aircraft_fleet` | Aircraft fleet inventory with type, registration, base, and status |
| 2 | `sarbanimaiti_catalog.pre_flight_dispatch.aircraft_certificates` | C of A and certificate validity tracking |
| 3 | `sarbanimaiti_catalog.pre_flight_dispatch.mel_items` | Minimum Equipment List deferred items |
| 4 | `sarbanimaiti_catalog.pre_flight_dispatch.crew_roster` | Crew assignments, qualifications, and duty hours |
| 5 | `sarbanimaiti_catalog.pre_flight_dispatch.flight_schedule` | Scheduled flights with routes, times, and assigned aircraft/crew |
| 6 | `sarbanimaiti_catalog.pre_flight_dispatch.weather_conditions` | Current and forecast weather at airports |
| 7 | `sarbanimaiti_catalog.pre_flight_dispatch.regulatory_requirements` | Regulatory compliance status and requirements |

To add each table:
- In the Genie Space configuration, click **Add Table**.
- Search for the table using the full three-level namespace (e.g., `sarbanimaiti_catalog.pre_flight_dispatch.aircraft_fleet`).
- Select the table and confirm.

## Step 3: Configure Sample Questions

Add the following sample questions to help users understand what the Genie Space can answer:

**Fleet & Aircraft Status:**
1. "Which aircraft are currently available for dispatch from DEL?"
2. "Show me all aircraft with expired certificates of airworthiness."
3. "List all Boeing 787 aircraft and their current maintenance status."

**MEL & Maintenance:**
4. "Which aircraft have MEL Category A deferrals that are approaching the 3-day repair limit?"
5. "Show all aircraft with more than 5 concurrent MEL deferrals."
6. "List overdue MEL items across the fleet."

**Crew & FDTL:**
7. "Which pilots are type-rated for A321neo and available for duty tomorrow?"
8. "Show crew members approaching the 30-hour weekly flight time limit."
9. "List all crew with expired medical certificates."
10. "Which crews have had less than 12 hours rest before their next duty?"

**Flight Schedule & Operations:**
11. "What flights are scheduled from DEL to BOM in the next 24 hours?"
12. "Show flights that don't have a crew assigned yet."
13. "Which flights are at risk due to crew duty time limitations?"

**Weather:**
14. "What is the current weather at BOM and DEL?"
15. "Are there any airports with visibility below ILS CAT I minima?"
16. "Show weather conditions that could affect today's departures from DEL."

**Cross-Domain Queries:**
17. "Give me the dispatch readiness status for flight AI-101 tomorrow."
18. "Which flights today have aircraft with open MEL items AND weather concerns at the destination?"

## Step 4: Set General Instructions (Optional)

In the Genie Space settings, add these general instructions to guide the AI:

```
You are an aviation operations intelligence assistant for Air India. When answering questions:

1. Always reference specific aircraft by their registration number (e.g., VT-ANA).
2. For crew queries, include license numbers and type ratings.
3. When discussing MEL items, always mention the deferral category (A/B/C/D) and remaining time until repair deadline.
4. For weather queries, interpret conditions against standard aviation minima (e.g., ILS CAT I: DH 200ft, RVR 550m).
5. Time references should use IST (Indian Standard Time, UTC+5:30) unless the user specifies otherwise.
6. Flag any safety-critical findings prominently (e.g., expired certificates, overdue ADs, crew duty time exceedances).
7. When asked about dispatch readiness, check across all dimensions: aircraft airworthiness, crew qualification and FDTL compliance, weather, and regulatory requirements.
```

## Step 5: Get the Genie Space ID

After creating the Genie Space:

1. Open the Genie Space in the browser.
2. Look at the URL — it will be in the format:
   ```
   https://adb-984752964297111.11.azuredatabricks.net/genie/rooms/<SPACE_ID>
   ```
3. Copy the `<SPACE_ID>` from the URL. This is the Genie Space ID.
4. This ID will be used in the agent configuration as the `genie_space_id` parameter for the Genie Agent tool.

**Example**: If the URL is `https://adb-984752964297111.11.azuredatabricks.net/genie/rooms/01f2a3b4c5d6e7f8`, then the Space ID is `01f2a3b4c5d6e7f8`.

## Step 6: Verify Access

1. Test a few sample questions in the Genie Space UI to confirm tables are queryable.
2. Verify that the service principal or user identity running the agents has access to the Genie Space.
3. Grant access if needed: **Genie Space Settings > Permissions > Add user/service principal**.

---

## Integration with Pre-Flight Dispatch V2

The Genie Space ID will be configured in the orchestrator's agent configuration (e.g., `agents/genie_agent.py` or in the YAML config) so the Genie Agent can programmatically query structured data through the Genie API:

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
# Start a Genie conversation
response = w.genie.start_conversation(
    space_id="<GENIE_SPACE_ID>",
    content="Which aircraft are available for dispatch from DEL?"
)
```

This allows the multi-agent orchestrator to delegate structured data queries to Genie while using Vector Search RAG for regulatory/unstructured document queries.
