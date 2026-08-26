# BusinessIntelligence.ai — Banking KPI Insight Engine (Prototype)

A demo-scoped implementation of the pipeline:

```
KPI movement → deterministic detection → driver attribution →
evidence → confidence/abstention → persona narrative → action → feedback
```

Built deliberately lean: no FastAPI layer, no vector DB, no forecasting,
no caching layer, no multi-agent intent routing. Streamlit calls the
Python modules directly, which read/write a local SQLite database.

## Why it's structured this way

| Layer | Deterministic or LLM? |
|---|---|
| KPI calculation, anomaly detection, materiality, contribution analysis, security, confidence scoring | **Deterministic** (SQL/Pandas/stats) |
| Evidence semantic classification, natural-language narrative, persona adaptation, conversational Q&A | **LLM** |

This boundary is shown explicitly on the "Insight Story" page (Method panel)
and is the core judging differentiator: the LLM never computes numbers,
it only explains numbers that were already computed deterministically.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate   # optional
pip install -r requirements.txt

cp .env.example .env
# edit .env and set an LLM_API_KEY (Gemini/OpenAI/Anthropic — see llm/client.py)

python db/init_db.py            # creates db/banking.db and loads schema
python data/generate_synthetic_data.py   # generates customers/RMs/transactions
python data/generate_documents.py        # generates ~40 evidence documents
python data/seed_scenarios.py            # engineers the 5 demo scenarios

streamlit run ui/app.py
```

If you don't set an LLM key, `llm/client.py` falls back to a deterministic
template-based narrative generator so the app still runs end-to-end offline.

## Project layout

See the file tree in the repository. Core modules:

- `analytics/kpi_calculator.py` — deterministic KPI math (SQL/Pandas)
- `analytics/detect.py` — baseline, deviation, z-score, materiality
- `analytics/attribute.py` — recursive contribution / driver-tree attribution
- `evidence/retrieval.py` — scoped, access-controlled document retrieval (no vector DB)
- `evidence/corroborate.py` — SUPPORTS/CONTRADICTS/NEUTRAL classification → confidence/abstention
- `llm/client.py` — thin LLM wrapper with latency/token/cost telemetry
- `llm/narrative.py` — turns validated analytics + evidence into persona narrative
- `recommend/engine.py` — maps driver + confidence → recommended action
- `feedback/feedback.py` — stores "was this useful" feedback
- `core/security.py` — RBAC entitlements + audit log (RM vs Branch Head vs Admin)
- `core/telemetry.py` — runtime, model calls, tokens, cost logging

## The 5 demo scenarios

Seeded by `data/seed_scenarios.py`:

- **A — Driver attribution**: Cross-Sell Revenue ↓12%, traced to Credit Cards → Salary Accounts → Unresolved Leads
- **B — Multi-factor decomposition**: Branch Revenue ↓10% = 50% volume / 30% mix / 20% pricing
- **C — Contradictory evidence**: Retention ↓, CRM says engagement dropped, market note says pricing changed → LOW CONFIDENCE
- **D — Sparse history**: Platinum Edge product launched 3 weeks ago → insufficient history → reduced confidence, peer benchmark used
- **E — Security**: RM-103 can see only their own book; attempting RM-108 data → ACCESS DENIED + audit event
