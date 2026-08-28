from core.models import (
    AttributionResult,
    ConfidenceResult,
    DetectionResult,
    DriverContribution,
    KPIResult,
)
from llm.narrative import offline_chat_response


def _context():
    kpi = KPIResult("cross_sell_revenue", "Cross-Sell Revenue", "2026-07", "BR-01", 80, 100, -0.2, "currency")
    detection = DetectionResult(kpi, -2.0, True, 0.2, "high", "baseline_zscore")
    attribution = AttributionResult(detection, [DriverContribution("credit_card", "Credit Card", 0.8)])
    confidence = ConfidenceResult(attribution, [], 0.2, "ABSTAIN", "no evidence")
    return {
        "user": "RM-103",
        "role": "relationship_manager",
        "branch_scope": "BR-01",
        "kpi": {"label": "Cross-Sell Revenue", "period": "2026-07", "actual": 80, "baseline": 100, "change_pct": -0.2},
        "detection": {"materiality_band": "high"},
        "drivers": [{"label": "Credit Card"}],
        "evidence": [],
        "confidence": {"band": confidence.confidence_band},
        "recommendation": {"action": "Review the account", "owner": "Branch Head"},
        "comparisons": {"same_month_last_year": 90, "prior_quarter_average": 95, "rolling_year_average": 92},
    }, confidence


def test_offline_chat_answers_movement_question():
    context, _ = _context()
    answer = offline_chat_response(type("Package", (), {"question": "What changed?"})(), context)
    assert "Cross-Sell Revenue" in answer
    assert "-20.0%" in answer


def test_offline_chat_answers_scope_question():
    context, _ = _context()
    answer = offline_chat_response(type("Package", (), {"question": "What is my access scope?"})(), context)
    assert "RM-103" in answer
    assert "own customers" in answer


def test_offline_chat_answers_branch_comparison():
    context, _ = _context()
    context["scope_comparisons"] = {
        "branches": [{"id": "BR-01", "kpi": 100}, {"id": "BR-02", "kpi": 120}],
    }
    answer = offline_chat_response(type("Package", (), {"question": "Compare the two branches"})(), context)
    assert "BR-01" in answer and "BR-02" in answer and "BR-02 is highest" in answer


def test_offline_chat_answers_rm_comparison():
    context, _ = _context()
    context["scope_comparisons"] = {
        "rms": [{"id": "RM-103", "kpi": 100}, {"id": "RM-108", "kpi": 120}],
    }
    answer = offline_chat_response(type("Package", (), {"question": "Which RM performs better?"})(), context)
    assert "RM-103" in answer and "RM-108" in answer and "RM-108 is highest" in answer