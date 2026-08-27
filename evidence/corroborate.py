"""Classifies each evidence doc as SUPPORTS / CONTRADICTS / NEUTRAL relative
to a driver hypothesis, then rolls that up into a confidence score/band.

Semantic classification is the one place the LLM is allowed to influence
evidence handling (per the LLM/deterministic boundary) — but every call
falls back to a transparent keyword heuristic if no LLM key is configured,
so the app still runs offline and the classification is always auditable.

confidence_score -> HIGH / MEDIUM / LOW / ABSTAIN
"""
import pathlib
import datetime as dt
import yaml
from core.models import AttributionResult, EvidenceItem, ConfidenceResult
from core.telemetry import timed_stage
from evidence.retrieval import retrieve_for_drivers
from llm.client import call_llm

ROOT = pathlib.Path(__file__).resolve().parent.parent
with open(ROOT / "config" / "source_registry.yaml") as f:
    _SOURCES = yaml.safe_load(f)["sources"]

CONTRADICT_HINTS = ["stable", "no change", "unaffected", "increased", "improved", "resolved"]
SUPPORT_HINTS = ["declined", "missed", "delay", "unresolved", "dropped", "churn", "complaint", "gap"]


def _classify_stance(driver_label: str, doc: dict) -> tuple:
    """Returns (stance, relevance 0..1, snippet). Tries LLM, falls back to keywords."""
    prompt = (
        "You are classifying whether a piece of evidence SUPPORTS, CONTRADICTS, "
        "or is NEUTRAL to a business hypothesis. Respond with exactly one word: "
        "SUPPORTS, CONTRADICTS, or NEUTRAL.\n\n"
        f"Hypothesis: '{driver_label}' is a driver of the KPI movement.\n"
        f"Evidence title: {doc['title']}\n"
        f"Evidence body: {doc['body']}\n"
    )
    result = call_llm(prompt, stage="evidence_classification", max_tokens=10)
    text = (result.get("text") or "").strip().upper()

    # Real LLMs sometimes add punctuation or a short lead-in even when told
    # to answer with exactly one word (e.g. "SUPPORTS." or "Answer: NEUTRAL").
    # Check by substring, most specific label first, before falling back to
    # the keyword heuristic — an exact-match-only check would silently treat
    # these as unparseable and skip the real classification.
    if "CONTRADICT" in text:
        stance = "CONTRADICTS"
    elif "SUPPORT" in text:
        stance = "SUPPORTS"
    elif "NEUTRAL" in text:
        stance = "NEUTRAL"
    else:
        # offline / unparseable fallback: keyword heuristic
        body_lower = doc["body"].lower()
        if any(h in body_lower for h in SUPPORT_HINTS):
            stance = "SUPPORTS"
        elif any(h in body_lower for h in CONTRADICT_HINTS):
            stance = "CONTRADICTS"
        else:
            stance = "NEUTRAL"

    relevance = 0.9 if stance != "NEUTRAL" else 0.5
    snippet = doc["body"][:180] + ("..." if len(doc["body"]) > 180 else "")
    return stance, relevance, snippet


def build_confidence(attribution: AttributionResult, branch_id: str = None,
                      product_code: str = None, user_id: str = None) -> ConfidenceResult:
    with timed_stage("corroborate"):
        detection = attribution.detection
        top_drivers = attribution.drivers[:3]

        evidence_by_driver = retrieve_for_drivers(
            top_drivers, branch_id=branch_id, product_code=product_code, user_id=user_id
        )

        all_evidence = []
        supports, contradicts = 0, 0
        for driver in top_drivers:
            docs = evidence_by_driver.get(driver.driver_key, [])
            for doc in docs:
                stance, relevance, snippet = _classify_stance(driver.label, doc)
                all_evidence.append(EvidenceItem(
                    doc_id=doc["doc_id"], title=doc["title"], source_type=doc["source_type"],
                    stance=stance, relevance=relevance, snippet=snippet,
                    created_on=doc.get("created_on"),
                    freshness_status=_freshness_status(doc),
                ))
                if stance == "SUPPORTS":
                    supports += 1
                elif stance == "CONTRADICTS":
                    contradicts += 1

        # --- confidence scoring ---
        base = 0.5
        if detection.sparse_history:
            base -= 0.25
        base += min(detection.materiality, 0.3)
        base += min(supports * 0.08, 0.3)
        base -= min(contradicts * 0.15, 0.4)
        score = max(0.0, min(1.0, base))

        rationale_parts = []
        if detection.sparse_history:
            rationale_parts.append("insufficient trailing history (sparse baseline)")
        if contradicts > 0 and supports > 0:
            rationale_parts.append(f"{contradicts} contradicting vs {supports} supporting evidence items")
        elif contradicts > 0:
            rationale_parts.append(f"{contradicts} contradicting evidence item(s), no corroboration")
        elif supports > 0:
            rationale_parts.append(f"{supports} corroborating evidence item(s)")
        else:
            rationale_parts.append("no directly matching evidence found")
        rationale_parts.append(f"materiality={detection.materiality_band}")
        rationale = "; ".join(rationale_parts)

        if contradicts > 0 and supports > 0 and abs(supports - contradicts) <= 1:
            band = "LOW"
        elif score >= 0.7:
            band = "HIGH"
        elif score >= 0.45:
            band = "MEDIUM"
        elif score >= 0.25:
            band = "LOW"
        else:
            band = "ABSTAIN"

        return ConfidenceResult(
            attribution=attribution,
            evidence=all_evidence,
            confidence_score=round(score, 3),
            confidence_band=band,
            rationale=rationale,
        )


def _freshness_status(doc: dict) -> str:
    source = _SOURCES.get(doc.get("source_type"), {})
    warning_days = source.get("freshness_days_warning")
    if not warning_days or not doc.get("created_on"):
        return "UNKNOWN"
    try:
        age_days = (dt.date.today() - dt.date.fromisoformat(doc["created_on"])).days
    except ValueError:
        return "UNKNOWN"
    return "FRESH" if age_days <= warning_days else "STALE"
