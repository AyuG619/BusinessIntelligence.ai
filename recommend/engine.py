"""Maps top driver + confidence band -> a recommended action.

Deterministic eligibility:
- Sparse-history driver -> always routes to the peer-benchmark template,
  regardless of confidence band (it's a known limitation with a defined
  mitigation, not a case for human review).
- Otherwise, LOW/ABSTAIN confidence routes to 'abstain_low_confidence'
  (human review), never to a normal action template.
- MEDIUM/HIGH confidence routes to the driver-specific action template.
"""
import sqlite3
import pathlib
import yaml
from core.models import ConfidenceResult, RecommendedAction

ROOT = pathlib.Path(__file__).resolve().parent.parent
with open(ROOT / "config" / "action_templates.yaml") as f:
    _CFG = yaml.safe_load(f)["actions"]

DB_PATH = ROOT / "db" / "banking.db"

# Maps driver_key patterns -> action template key
_DRIVER_TO_TEMPLATE = {
    "lead_status_open": "unresolved_leads",
    "lead_status_lost": "unresolved_leads",
    "credit_card": "credit_card_dropoff",
    "pricing": "pricing_pressure",
    "mix": "pricing_pressure",
    "engagement": "engagement_decline",
    "sparse_history_new_product": "sparse_history_new_product",
}


def _template_for_driver(driver_key: str) -> str:
    for pattern, template in _DRIVER_TO_TEMPLATE.items():
        if pattern in driver_key:
            return template
    return "engagement_decline"  # generic fallback


def _resolve_action_text(tmpl: dict, persona: str, **fmt_kwargs) -> str:
    """Resolve a persona override while preserving the base template fallback."""
    persona_map = tmpl.get("persona_actions") or {}
    template_str = persona_map.get(persona, tmpl["action"])
    return template_str.format(**fmt_kwargs)


def _count_unresolved_leads(product_code: str = None, branch_id: str = None, db_path=DB_PATH) -> int:
    conn = sqlite3.connect(db_path)
    try:
        clauses, params = ["status = 'open'"], []
        if product_code:
            clauses.append("product_code = ?")
            params.append(product_code)
        if branch_id:
            clauses.append("branch_id = ?")
            params.append(branch_id)
        q = f"SELECT COUNT(*) FROM leads WHERE {' AND '.join(clauses)}"
        return conn.execute(q, params).fetchone()[0]
    finally:
        conn.close()


def recommend(confidence: ConfidenceResult, branch_id: str = None,
              product_code: str = None, persona: str = None,
              db_path=DB_PATH) -> RecommendedAction | None:
    band = confidence.confidence_band
    top_driver = confidence.attribution.drivers[0] if confidence.attribution.drivers else None

    # Sparse-history is a known, well-understood limitation with a defined
    # mitigation (peer benchmarking) — it is NOT the same situation as
    # genuinely contradictory evidence, so it must not be swallowed by the
    # generic "abstain, send to human review" path even though its
    # confidence score is also LOW. Check this before the general band gate.
    if top_driver is not None and top_driver.driver_key == "sparse_history_new_product":
        tmpl = _CFG["sparse_history_new_product"]
        return RecommendedAction(
            driver_key=top_driver.driver_key, lever=tmpl["lever"],
            action=_resolve_action_text(tmpl, persona),
            owner=tmpl["owner"], monitoring_kpi=tmpl["monitoring_kpi"],
        )

    if band in ("LOW", "ABSTAIN"):
        tmpl = _CFG["abstain_low_confidence"]
        return RecommendedAction(
            driver_key="abstain", lever=tmpl["lever"],
            action=_resolve_action_text(tmpl, persona),
            owner=tmpl["owner"], monitoring_kpi=tmpl["monitoring_kpi"],
        )

    if top_driver is None:
        return None

    template_key = _template_for_driver(top_driver.driver_key)
    tmpl = _CFG[template_key]

    n = _count_unresolved_leads(product_code, branch_id, db_path) if "{n}" in tmpl["action"] else None
    action_text = _resolve_action_text(
        tmpl, persona, n=n or 0, product=product_code or "cross-sell"
    )

    return RecommendedAction(
        driver_key=top_driver.driver_key,
        lever=tmpl["lever"],
        action=action_text,
        owner=tmpl["owner"],
        monitoring_kpi=tmpl["monitoring_kpi"],
    )
