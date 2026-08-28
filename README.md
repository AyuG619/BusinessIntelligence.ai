# BusinessIntelligence.ai

BusinessIntelligence.ai is a prototype for turning banking KPI movement into an evidence-backed decision:

```text
KPI movement -> deterministic detection -> driver attribution
-> scoped evidence -> confidence/abstention -> narrative -> action -> feedback
```

SQL, Pandas, statistics, access control, confidence scoring, and recommendation eligibility are deterministic. Groq is used only for evidence stance classification and persona-adapted narrative generation. The LLM never calculates KPI values or makes security decisions.

## Quickstart

Run commands from the repository root:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

python db/init_db.py
python data/generate_synthetic_data.py
python data/generate_documents.py
python data/seed_scenarios.py

streamlit run ui/app.py
```

The setup scripts are intentionally ordered. Synthetic baseline data must be created before the scenario overlay is used.

## Groq configuration

Create `.env` in the repository root:

```env
LLM_PROVIDER=groq
LLM_MODEL=qwen/qwen3.8-27b
LLM_API_KEY=your_groq_api_key
DB_PATH=db/banking.db
```

The client calls Groq's OpenAI-compatible endpoint:
`https://api.groq.com/openai/v1/chat/completions`.

Restart Streamlit after changing `.env`; configuration is loaded when `llm/client.py` is imported. If the key or provider is unavailable, the app falls back to a deterministic local narrative and keyword evidence classifier. The UI labels that output as offline mode.

## User workflow

### Command center

The entry page, [ui/app.py](ui/app.py), provides sidebar navigation, demo user selection, date/branch/product/segment filters, cached SQLite loading, live metrics, Plotly trend and product-mix views, a transaction table, CSV download, and deterministic scope summaries. Conversational analysis is intentionally kept on the dedicated Ask your data page described below.

### KPI Overview

[KPI Overview](ui/pages/1_KPI_Overview.py) calculates four live KPI results and groups the result into signal, alert, and data-note tabs.

### Insight Story

[Insight Story](ui/pages/2_Insight_Story.py) is the main judging workflow:

1. Select a KPI or Platinum Edge launch KPI.
2. Compare the current value with a trailing baseline.
3. Attribute the movement by product or volume/mix/pricing.
4. Retrieve scoped evidence from SQLite.
5. Classify evidence with Groq as SUPPORTS, CONTRADICTS, or NEUTRAL.
6. Calculate confidence and abstain when evidence is weak or contradictory.
7. Generate a persona-specific narrative with Groq.
8. Show a recommended action and capture usefulness feedback.

The page also includes Method and model telemetry and KPI contract and lineage expanders.

### Ask your data

[Ask your data](ui/pages/3_Conversational.py) is a dedicated conversational
banking analyst, not a collection of one-shot KPI buttons. It uses
`st.chat_input` and `st.chat_message`, preserves the conversation, and passes
the user's question plus the last four question/answer pairs into a Groq
prompt. The selected KPI package remains the governed source of facts, while
Groq answers the user's actual question using the validated context.

The assistant can discuss the current KPI, baseline, movement, drivers,
evidence, freshness, confidence, recommendations, financial-year comparisons,
branch scope, and role restrictions. Admin users receive explicit KPI values
for both BR-01 and BR-02 and can compare branch performance. Branch Heads
receive explicit KPI values for each RM in their own branch and can compare RM
performance. Relationship Managers see only their authorized portfolio.

When Groq is unavailable, the page uses a deterministic fallback that answers
only supported questions from the validated context. Unsupported questions
receive a clear scope message instead of a fabricated answer.

### Security & access

[Security Demo](ui/pages/4_Security_Demo.py) demonstrates RM, Branch Head, and Admin access rules. Allowed and denied customer, branch, and sensitive-field checks are written to the SQLite audit log.

Role scope is explicit throughout the app: Admin has global branch and
customer access; a Branch Head has all customer and RM performance data in
their own branch; each Relationship Manager has only their own customers and
portfolio metrics. Branch-level comparisons are Admin-only, while RM-level
comparisons are available to Admins and Branch Heads.

## KPI contract

[config/kpi_definitions.yaml](config/kpi_definitions.yaml) defines the four registered KPIs and includes labels, roles, units, source tables, filters, numerator/denominator rules, grouping, direction, materiality thresholds, drivers, lineage, access scope, and intended refresh cadence.

The calculation implementation is in [analytics/kpi_calculator.py](analytics/kpi_calculator.py). The contract is lightweight metadata, not an ORM or semantic-layer runtime.

| KPI | Source | Grain | Main calculation |
|---|---|---|---|
| Cross-Sell Revenue | `revenue_transactions` | transaction/month/branch | Sum cross-sell amount |
| Lead Conversion Rate | `leads` | lead/created-month/branch | Converted leads / all leads |
| Customer Retention Rate | `customers` | customer/onboarded-month/branch | Active customers / cohort |
| Revenue Per Customer | `revenue_transactions` + customer ID | transaction/month/branch | Revenue / distinct customers |

## Source registry and freshness

[config/source_registry.yaml](config/source_registry.yaml) records source labels, grain, intended refresh cadence, trust weight, and warning age. Evidence documents carry `created_on`; [evidence/corroborate.py](evidence/corroborate.py) calculates `FRESH`, `STALE`, or `UNKNOWN` using the source warning window. Evidence cards display the status and creation date.

The prototype simulates cadence metadata; it does not run separate ingestion jobs. Operational synthetic data is stored in SQLite, while the marketing export is maintained as a separate CSV source. A production version would connect the registry to ingestion timestamps and freshness checks.

The prototype also includes a separate `data/marketing_campaigns.csv` export
at campaign/month/branch grain. `analytics/reconciliation.py` compares its
conversion totals with SQLite's lead-grain records and reports `RECONCILED` or
`REVIEW`, including source as-of time and grain.

## Personas and actions

[config/personas.yaml](config/personas.yaml) defines Relationship Manager, Branch Head, and Executive personas with different tone and detail levels. [llm/narrative.py](llm/narrative.py) puts the selected persona into the Groq prompt.

Recommendation eligibility remains deterministic and is based on the driver and confidence band. Action text is also customized by persona: relationship managers receive tactical instructions, branch heads receive operational direction, and executives receive concise strategic framing.

Feedback closes a bounded learning loop: after three ratings for a KPI, the
useful/not-useful balance can adjust confidence by at most +/-0.10. Evidence
requirements and contradiction rules still take precedence, and any applied
adjustment is recorded in the confidence rationale.

## Recent framework improvements

- **Evidence-required confidence:** a movement with no retrievable evidence is
	forced to `ABSTAIN`, regardless of materiality, so unsupported drivers cannot
	trigger a normal recommendation.
- **Customer-level evidence security:** relationship managers can retrieve
	customer-scoped documents only for their own customers; branch heads are
	restricted to customers in their branch; admins retain global scope.
- **Strict stance validation:** LLM evidence classification accepts only a
	complete `SUPPORTS`, `CONTRADICTS`, or `NEUTRAL` response, with deterministic
	keyword fallback for malformed or offline responses.
- **Traceable recommendations:** engagement actions no longer claim a numeric
	customer count unless that metric is actually calculated by the engine.
- **Cross-source reconciliation:** the marketing CSV and CRM lead table use
	different grains and are compared explicitly, with mismatches marked
	`REVIEW` rather than silently merged.
- **Bounded feedback learning:** analyst and user ratings influence confidence
	only after a minimum sample and cannot override evidence or contradiction
	rules.

## Demo scenarios and expected output

[data/seed_scenarios.py](data/seed_scenarios.py) creates five scenarios:

- **A: Product attribution** — cross-sell revenue declines; Credit Card and unresolved leads appear as drivers.
- **B: Multi-factor bridge** — revenue movement decomposes into volume, mix, and pricing effects. The three effects should reconstruct the total delta.
- **C: Conflicting evidence** — retention declines while engagement, pricing, and survey evidence disagree. Expected result: LOW/ABSTAIN confidence and human-review recommendation.
- **D: Sparse history** — Platinum Edge has current-month-only data. Expected result: sparse-history flag and peer-benchmark recommendation.
- **E: Security** — RM-103 cannot access RM-108's customer; the denied attempt creates an audit event.

## LLM versus deterministic boundary

| Stage | Implementation | LLM? |
|---|---|---|
| KPI calculation | SQL/Pandas | No |
| Detection | Baseline, z-score, materiality | No |
| Attribution | Product and volume/mix/pricing arithmetic | No |
| Evidence retrieval | Scoped SQLite keyword filtering | No |
| Evidence stance | Groq classification with keyword fallback | Yes |
| Confidence | Rule-based score and band | No |
| Recommendation eligibility | Rule-based confidence gate | No |
| Narrative | Groq persona-adapted explanation | Yes |
| Security | Deterministic RBAC | No |

## Runtime telemetry

[core/telemetry.py](core/telemetry.py) stores stage duration, model, token estimates, estimated cost, and timestamp in `telemetry_log`.

Insight Story reports the current model and latency, current token/cost estimates, persistent model-call count, persistent pipeline-event count, and aggregate latency/tokens/cost. `model_calls` counts records with a model name; `pipeline_events` includes all timed stages as well as model calls.

## Database

[db/schema.sql](db/schema.sql) creates dimensions (`branches`, `relationship_managers`, `customers`), operational facts (`product_holdings`, `leads`, `revenue_transactions`), evidence/feedback tables, audit and telemetry tables, and `kpi_snapshots`. `kpi_snapshots` exists for a future cache but is not used for headline KPIs.

## Tests

Run:

```powershell
pytest -q
```

The suite covers KPI detection, product attribution, volume/mix/pricing decomposition, contradictory evidence, sparse history, confidence-gated recommendations, RBAC, source reconciliation, feedback adjustment, deterministic chat fallback, and role-aware branch/RM comparisons.

The synthetic generator creates 36 complete monthly periods. This supports
same-month-last-year, prior-quarter-average, and prior-rolling-year comparisons
in Insight Story. The visible period label includes the financial year, for
example `FY 2026-27 · 2026-07`; the underlying `YYYY-MM` value remains the
stable calculation key.

The generated database contains two branches. BR-01 and BR-02 each have four
relationship managers and 60 customers. BR-02 includes 29 leads, 1,074 revenue
transactions, and the same 36-month transaction history as BR-01. The seeded
evidence set is intentionally concentrated on BR-01 for the primary demo;
BR-02 has baseline operational data and limited branch-specific evidence.

## Feasibility summary

Implemented:

- Four connected KPIs across transaction, lead, and customer grains.
- KPI definitions, thresholds, drivers, lineage, access scope, and cadence metadata.
- Three narrative personas.
- Multi-factor movement, low-confidence abstention, sparse history, and RBAC scenarios.
- Evidence freshness status, contribution, confidence, method, and lineage display.
- Deterministic conversational answers with authorized branch and RM comparisons.
- Groq/non-Groq processing boundary.
- Latency, model-call, token, and estimated-cost telemetry.

Still prototype-level:

- Refresh cadence is metadata only; there are no independent source pipelines.
- Conversational question understanding remains intentionally bounded to supported deterministic queries when offline.
- SQLite keyword retrieval is not semantic/vector retrieval.
- Token counts and costs are estimates, not provider billing records.
- Demo users and database data are synthetic; production authentication and deployment controls are not included.
