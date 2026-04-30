# Air India AI Agent Demos

Multi-agent AI systems for airline operations built on Databricks — demonstrating how AI agents can transform flight dispatch and aircraft maintenance.

## Demos

### 1. Pre-Flight Readiness & Dispatch Agent (V2)
A production-grade multi-agent system that performs pre-flight readiness checks across 4 dimensions — aircraft health, crew legality, weather, and regulatory compliance — delivering a Go/No-Go decision in seconds instead of the 40+ minutes it takes manually.

### 2. Predictive Maintenance Orchestrator
AI agents that predict aircraft component failures from sensor telemetry and automatically orchestrate work orders, parts logistics, and maintenance scheduling.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     DISPATCH DASHBOARD                           │
│                    (Databricks App)                               │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│               DISPATCH SUPERVISOR                                │
│           (LangGraph State Machine)                              │
│        Sequential → Conditional Routing                          │
└──┬──────────┬──────────┬──────────┬──────────┬─────────────────┘
   │          │          │          │          │
   ▼          ▼          ▼          ▼          ▼
┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────────┐
│AirSafe│  │Crew  │  │Sky   │  │Compli│  │Fleet     │
│Agent  │  │Watch │  │Watch │  │ance  │  │Insight   │
│       │  │Agent │  │Agent │  │Guard │  │Agent     │
│MEL,AD │  │DGCA  │  │Live  │  │COA,  │  │Genie     │
│C-Check│  │FDTL  │  │METAR │  │ETOPS │  │NL→SQL    │
└──┬──┬─┘  └──┬──┘  └──┬──┘  └──┬──┘  └─────┬────┘
   │  │       │        │        │             │
   │  │  ┌────▼────┐   │   ┌───▼────┐   ┌───▼────┐
   │  │  │crew_    │   │   │certif- │   │Genie   │
   │  │  │roster   │   │   │icates  │   │Space   │
   │  │  │(UC)     │   │   │(UC)    │   │        │
   ▼  ▼  └────────┘   ▼   └───────┘   └────────┘
┌──────┐          ┌──────────┐
│MEL,  │          │Open-Meteo│
│fleet │          │Weather   │
│(UC)  │          │API       │
└──────┘          └──────────┘
   │
   ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│DGCA CARs     │  │Airworthiness │  │Dispatch SOPs │
│(Vector Search)│  │Directives(VS)│  │(Vector Search)│
└──────────────┘  └──────────────┘  └──────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│  DecisionBrain (GPT-OSS-120B) → SafetyNet (18 Guardrails)      │
│  MLflow Tracing │ Token Tracking │ Quality Scoring               │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                  ┌────────▼────────┐
                  │  GO / NO-GO /   │
                  │  CONDITIONAL    │
                  └────────┬────────┘
                           │
              ┌────────────▼────────────┐
              │ Assign Crew → Notify →  │
              │ Generate Dispatch Release│
              │ NO-GO → CONDITIONAL → GO│
              └─────────────────────────┘
```

---

## Project Structure

```
airlines-agent/
├── pre-flight-dispatch-v2/          # Main demo (V2 multi-agent)
│   ├── app.py                       # FastAPI application
│   ├── app.yaml                     # Databricks App config
│   ├── config.py                    # Central configuration
│   ├── requirements.txt
│   │
│   ├── orchestrator/                # Supervisor orchestration
│   │   ├── supervisor.py            # LangGraph state machine + MLflow tracing
│   │   ├── state.py                 # TypedDict state definition
│   │   └── router.py               # Conditional routing logic
│   │
│   ├── agents/                      # 5 Specialized agents
│   │   ├── aircraft_health.py       # AirSafe Agent (MEL, AD, C-Check)
│   │   ├── crew_legality.py         # CrewWatch Agent (DGCA FDTL, fatigue)
│   │   ├── weather_notam.py         # SkyWatch Agent (live METAR)
│   │   ├── regulatory_compliance.py # ComplianceGuard Agent (COA, ETOPS)
│   │   └── genie_agent.py           # FleetInsight Agent (Genie NL→SQL)
│   │
│   ├── tools/                       # Shared tool layer
│   │   ├── sql_tools.py             # Unity Catalog SQL via SDK
│   │   ├── llm_tools.py             # LLM via ai_query + token tracking
│   │   ├── vector_search_tools.py   # Vector Search RAG
│   │   ├── weather_api.py           # Open-Meteo real-time weather
│   │   └── genie_tools.py           # Genie Space integration
│   │
│   ├── guardrails/                  # Safety system
│   │   ├── safety_rules.py          # 18 hard-coded safety rules
│   │   ├── input_validator.py       # Prompt injection detection
│   │   └── output_validator.py      # Decision validation + LLM override
│   │
│   ├── evaluation/                  # MLflow evaluation framework
│   │   ├── scorers.py               # 12 scorers (4 LLM-judge + 3 guidelines + 5 code)
│   │   ├── run_eval.py              # Evaluation runner
│   │   ├── api.py                   # Eval API endpoints
│   │   └── scenarios/               # 50 labeled test scenarios
│   │       ├── go_scenarios.json
│   │       ├── nogo_scenarios.json
│   │       └── conditional_scenarios.json
│   │
│   ├── data/                        # Data setup
│   │   ├── documents/               # Regulatory docs for Vector Search
│   │   │   ├── dgca_car_ops.md
│   │   │   ├── airworthiness_directives.md
│   │   │   └── dispatch_sops.md
│   │   ├── seed_unstructured.py     # Vector Search index creation
│   │   └── genie_setup.md           # Genie Space setup guide
│   │
│   ├── static/                      # Dashboard UI
│   │   ├── index.html               # Main dispatch dashboard
│   │   ├── vision.html              # CXO roadmap presentation
│   │   ├── style.css
│   │   └── app.js
│   │
│   └── docs/
│       ├── architecture.dot         # Architecture diagram source
│       └── architecture.png         # Architecture diagram image
│
├── pre-flight-dispatch/             # V1 (original, simpler)
│   ├── app.py
│   ├── agents/
│   └── static/
│
├── predictive-maintenance/          # Predictive Maintenance demo
│   ├── app.py
│   ├── agents/
│   │   ├── anomaly_detection.py
│   │   ├── work_order.py
│   │   ├── parts_inventory.py
│   │   └── schedule_alignment.py
│   └── static/
│
├── .gitignore
└── README.md
```

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| **Orchestration** | LangGraph State Machine (with sequential fallback) |
| **LLM** | GPT-OSS-120B via Databricks AI Gateway (`ai_query` SQL function) |
| **Structured Data** | Unity Catalog (Delta tables, SQL Statement Execution API) |
| **Unstructured Data** | Databricks Vector Search (databricks-gte-large-en embeddings) |
| **Real-time Weather** | Open-Meteo API (13 airports, no API key required) |
| **Analytics** | Genie Space (NL→SQL for flight ops) |
| **Guardrails** | 18 deterministic safety rules + hallucination detection |
| **Tracing** | MLflow (per-agent spans, LLM calls, SQL, VS, Weather API) |
| **Evaluation** | 12 scorers (4 LLM-judge + 3 guidelines + 5 code-based), 50 scenarios |
| **Token Tracking** | Per-call input/output tokens, cost estimation |
| **App Framework** | Databricks Apps (FastAPI + vanilla JS dashboard) |
| **Embedding** | databricks-gte-large-en |

---

## Prerequisites

- Databricks workspace (Azure) with:
  - Unity Catalog enabled
  - SQL Warehouse (serverless)
  - Foundation Model API access (GPT-OSS-120B)
  - Vector Search endpoint
  - Databricks Apps enabled
- Databricks CLI v0.285+
- Python 3.10+

---

## Installation & Setup

### Step 1: Clone the repo

```bash
git clone https://github.com/sarbaniAi/airlines-agent.git
cd airlines-agent
```

### Step 2: Configure your workspace

Create a `.env.local` file (not tracked by git) with your workspace details:

```bash
# .env.local
WORKSPACE_URL=https://your-workspace.azuredatabricks.net
DATABRICKS_PROFILE=your-profile
CATALOG=your_catalog
SCHEMA=pre_flight_dispatch
SQL_WAREHOUSE_ID=your-warehouse-id
```

Update `pre-flight-dispatch-v2/config.py` with your values:

```python
CATALOG = "your_catalog"
SCHEMA = "pre_flight_dispatch"
WAREHOUSE_ID = "your-warehouse-id"
VS_ENDPOINT = "your-vs-endpoint"
LLM_MODEL = "databricks-gpt-oss-120b"  # or your preferred model
```

### Step 3: Authenticate with Databricks CLI

```bash
databricks auth login --host https://your-workspace.azuredatabricks.net --profile your-profile
```

### Step 4: Create Unity Catalog schema

```sql
CREATE SCHEMA IF NOT EXISTS your_catalog.pre_flight_dispatch;
CREATE SCHEMA IF NOT EXISTS your_catalog.predictive_maintenance;
```

### Step 5: Seed structured data

The seed data includes:
- 15 aircraft (Boeing 787, A321neo, B777, A320neo)
- 52 certificates (COA, RVSM, ETOPS, Airworthiness)
- 24 crew members (captains, first officers, senior FOs)
- 20 MEL items (Category A through D)
- 10 flights (DEL, BOM, BLR, YYZ, LHR, JFK, SFO)
- 9 weather stations
- 17 regulatory requirements (India, Canada, UK, US, Singapore)

Load from the Lakebase seed SQL or create tables directly in Unity Catalog:

```bash
# Option A: Use the seed script (requires Lakebase)
cd pre-flight-dispatch-v2
python data/seed_unstructured.py

# Option B: Load via SQL warehouse (see data/seed_data.sql in pre-flight-dispatch/)
```

### Step 6: Create Vector Search index

```bash
cd pre-flight-dispatch-v2
DATABRICKS_CONFIG_PROFILE=your-profile python data/seed_unstructured.py
```

This creates:
- Delta table `your_catalog.pre_flight_dispatch.regulatory_docs` (111 chunks)
- Vector Search index on your endpoint with `databricks-gte-large-en` embeddings

Documents indexed:
- DGCA Civil Aviation Requirements (flight duty time limits, airworthiness, crew quals)
- 10 Airworthiness Directives (B787, A321, B777, A320, general)
- 7 Dispatch SOPs (250+ item checklist, Go/No-Go criteria, crew swap procedures)

### Step 7: Create MLflow experiment

```bash
# Via CLI
databricks experiments create --name "/Users/your-email/pre-flight-dispatch-v2" --profile your-profile

# Grant your app's service principal CAN_MANAGE on the experiment
```

### Step 8: Create Databricks App

```bash
# Create the app (if not exists)
databricks apps create your-app-name --profile your-profile

# Sync source code
databricks sync pre-flight-dispatch-v2 \
  /Users/your-email/air-india-demos/pre-flight-dispatch-v2 \
  --profile your-profile --watch=false --full

# Deploy
databricks apps deploy your-app-name \
  --source-code-path /Workspace/Users/your-email/air-india-demos/pre-flight-dispatch-v2 \
  --profile your-profile
```

### Step 9: Grant permissions to app service principal

The app's service principal needs access to:

```sql
-- Unity Catalog
GRANT ALL PRIVILEGES ON CATALOG your_catalog TO `<sp-client-id>`;
GRANT ALL PRIVILEGES ON SCHEMA your_catalog.pre_flight_dispatch TO `<sp-client-id>`;

-- SQL Warehouse (via REST API)
-- PATCH /api/2.0/permissions/sql/warehouses/<warehouse-id>
-- with service_principal_name and CAN_USE permission
```

### Step 10: Verify

```bash
# Check health
curl https://your-app-url/api/health

# Expected:
# {"status":"healthy","version":"2.0.0","database":"connected",
#  "vector_search":"connected","llm":"connected","flight_count":10}
```

---

## Usage

### Run a Dispatch Check

```bash
curl -X POST https://your-app-url/api/dispatch-check \
  -H "Content-Type: application/json" \
  -d '{"flight_id": "AI-302"}'
```

### Test Flights

| Flight | Route | Expected | Scenario |
|--------|-------|----------|----------|
| AI-191 | DEL→SFO | GO | All green, crew qualified, certs valid |
| AI-680 | DEL→BOM | CONDITIONAL | Minor MEL items (AMBER), domestic |
| AI-302 | DEL→YYZ | NO-GO | Expired Canada COA, crew duty limits, MEL |

### Chat with Crew Enrichment

```bash
curl -X POST https://your-app-url/api/chat \
  -H "Content-Type: application/json" \
  -d '{"flight_id": "AI-302", "message": "who can replace FO Arjun Kapoor?"}'
```

Returns specific eligible crew members with duty hours, rest, fatigue, and route qualifications.

### Phase 1 Actions

After a dispatch check:

```bash
# Assign replacement crew
curl -X POST /api/assign-crew -d '{"flight_id":"AI-302","crew_name":"FO Isha Mehta","crew_rank":"FIRST_OFFICER","replacing":"FO Arjun Kapoor"}'

# Notify crew via SMS
curl -X POST /api/notify-crew -d '{"flight_id":"AI-302","crew_name":"FO Isha Mehta"}'

# Generate amended dispatch release
curl -X POST /api/generate-release -d '{"flight_id":"AI-302"}'
```

Status progresses: **NO-GO → CONDITIONAL → GO** as actions are completed.

### Token Usage

```bash
curl https://your-app-url/api/token-usage
```

### Run Evaluation

```bash
curl -X POST https://your-app-url/api/run-eval?category=nogo&max_scenarios=3
```

---

## Evaluation Framework

### 12 Scorers

| # | Scorer | Type | What It Measures |
|---|--------|------|------------------|
| 1 | answer_correctness | LLM-judge | Decision matches expected? |
| 2 | faithfulness | LLM-judge | Reasoning grounded in data? |
| 3 | relevance | LLM-judge | Findings specific to this flight? |
| 4 | chunk_relevance | LLM-judge | RAG chunks actually useful? |
| 5 | decision_correctness | Guidelines | GO/NO-GO exact match |
| 6 | safety_compliance | Guidelines | All RED items caught? |
| 7 | guardrail_accuracy | Guidelines | Correct rules triggered? |
| 8 | completeness | Code | All 4 agents reported? |
| 9 | recommendation_quality | Code | Specific names/regs cited? |
| 10 | latency_budget | Code | Under 30s threshold? |
| 11 | regulatory_citation | Code | DGCA/TCCA references? |
| 12 | action_specificity | Code | Actionable crew/aircraft names? |

### 50 Test Scenarios

- 15 GO scenarios (all systems green)
- 20 NO-GO scenarios (expired certs, crew violations, weather RED)
- 15 CONDITIONAL scenarios (multiple AMBER findings)

---

## Safety Guardrails

18 deterministic rules that override the LLM:

| Rule | Trigger | Action |
|------|---------|--------|
| SR-001 | Expired regulatory certificate | NO-GO |
| SR-002 | Expired medical certificate | NO-GO |
| SR-003 | Expired airworthiness certificate | NO-GO |
| SR-004 | Aircraft not serviceable | NO-GO |
| SR-005 | MEL Cat-A expired | NO-GO |
| SR-006 | C-check overdue | NO-GO |
| SR-007 | Crew duty 7-day exceeded | NO-GO |
| SR-008 | Crew duty 28-day exceeded | NO-GO |
| SR-009 | Insufficient crew rest | NO-GO |
| SR-010 | Crew fatigue critical | NO-GO |
| SR-011 | Missing route qualification | NO-GO |
| SR-012 | Weather below minimums (origin) | NO-GO |
| SR-013 | Weather below minimums (dest) | NO-GO |
| SR-014 | Thunderstorm active | CONDITIONAL |
| SR-015 | Insurance expired | NO-GO |
| SR-016 | Crew medical expiring (30d) | CONDITIONAL |
| SR-017 | Multiple AMBER findings | CONDITIONAL |
| SR-018 | Aircraft high flight hours | CONDITIONAL |

---

## MLflow Tracing

Every dispatch check creates an MLflow run with:

**Spans (nested trace tree):**
- Supervisor → AirSafe Agent → SQL queries + Vector Search
- Supervisor → CrewWatch Agent → SQL queries + Vector Search
- Supervisor → SkyWatch Agent → Weather API call
- Supervisor → ComplianceGuard Agent → SQL queries + Vector Search
- Supervisor → DecisionBrain → LLM call (GPT-OSS-120B)

**Metrics logged:**
- Per-agent status (0=GREEN, 1=AMBER, 2=RED) and finding counts
- Decision confidence, execution time
- Quality scores (completeness, recommendation quality, latency, regulatory citation, action specificity)

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Dashboard UI |
| GET | `/static/vision.html` | CXO roadmap presentation |
| GET | `/api/health` | System health (DB, VS, LLM) |
| GET | `/api/flights` | List all flights |
| GET | `/api/flight/{id}` | Flight details |
| POST | `/api/dispatch-check` | Run multi-agent dispatch check |
| POST | `/api/chat` | Follow-up chat with crew enrichment |
| POST | `/api/assign-crew` | Assign replacement crew |
| POST | `/api/notify-crew` | Send SMS notification (simulated) |
| POST | `/api/generate-release` | Generate dispatch release document |
| GET | `/api/dispatch-actions/{id}` | Action tracker status |
| GET | `/api/token-usage` | Session token usage stats |
| POST | `/api/run-eval` | Run evaluation pipeline |
| GET | `/api/eval-results` | Latest evaluation results |
| GET | `/api/eval-scenarios` | List test scenarios |

---

## License

Internal Databricks Field Engineering demo. Not for external distribution.
