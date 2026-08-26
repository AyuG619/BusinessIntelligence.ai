"""End-to-end smoke tests for the 5 demo scenarios — verifies the full
pipeline runs and produces the expected qualitative shape of result."""
import pathlib
import sys
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from analytics.kpi_calculator import (  # noqa: E402
    latest_kpi_result, compute_product_revenue_series, latest_product_kpi_result,
)
from analytics.detect import detect  # noqa: E402
from analytics.attribute import (  # noqa: E402
    attribute_by_product, attribute_volume_mix_price, attribute_retention_drivers,
    attribute_new_product_launch,
)
from evidence.corroborate import build_confidence  # noqa: E402
from recommend.engine import recommend  # noqa: E402

DB_PATH = ROOT / "db" / "banking.db"
pytestmark = pytest.mark.skipif(
    not DB_PATH.exists(), reason="db/banking.db not initialized — run setup scripts first"
)


def test_scenario_a_driver_attribution():
    kpi = latest_kpi_result("cross_sell_revenue", branch_id="BR-01")
    detection = detect(kpi)
    attribution = attribute_by_product(detection)
    assert kpi.change_pct < 0, "Scenario A expects cross-sell revenue to be down"
    assert any(d.driver_key == "credit_card" for d in attribution.drivers)


def test_scenario_b_volume_mix_price_decomposition():
    kpi = latest_kpi_result("cross_sell_revenue", branch_id="BR-01")
    detection = detect(kpi)
    attribution = attribute_volume_mix_price(detection)
    driver_keys = {d.driver_key for d in attribution.drivers}
    assert driver_keys.issubset({"volume", "mix", "pricing"})


def test_scenario_c_contradictory_evidence_lowers_confidence():
    kpi = latest_kpi_result("customer_retention_rate", branch_id="BR-01")
    detection = detect(kpi)
    assert kpi.change_pct < 0, "Scenario C expects retention to be down for the current cohort"
    attribution = attribute_retention_drivers(detection)
    confidence = build_confidence(attribution, branch_id="BR-01")
    # with contradictory evidence seeded (engagement decline vs stable pricing-driven churn),
    # confidence should not be HIGH
    assert confidence.confidence_band in ("LOW", "MEDIUM", "ABSTAIN")


def test_scenario_d_sparse_history_flagged():
    series = compute_product_revenue_series("platinum_edge", branch_id="BR-01")
    kpi = latest_product_kpi_result("platinum_edge", "Platinum Edge Revenue", branch_id="BR-01")
    detection = detect(kpi, series_df=series)
    assert detection.sparse_history is True, "Platinum Edge has only 1 month of history"


def test_scenario_d_routes_to_peer_benchmark_not_generic_abstain():
    """Sparse history is a known limitation with a defined mitigation — it
    must not fall into the generic 'send to human review' abstain path even
    though its confidence score is also low."""
    series = compute_product_revenue_series("platinum_edge", branch_id="BR-01")
    kpi = latest_product_kpi_result("platinum_edge", "Platinum Edge Revenue", branch_id="BR-01")
    detection = detect(kpi, series_df=series)
    attribution = attribute_new_product_launch(detection)
    confidence = build_confidence(attribution, branch_id="BR-01", product_code="platinum_edge")
    action = recommend(confidence, branch_id="BR-01", product_code="platinum_edge")
    assert action is not None
    assert action.driver_key == "sparse_history_new_product"
    assert "benchmark" in action.action.lower()


def test_scenario_e_recommendation_gated_by_confidence():
    kpi = latest_kpi_result("customer_retention_rate", branch_id="BR-01")
    detection = detect(kpi)
    attribution = attribute_retention_drivers(detection)
    confidence = build_confidence(attribution, branch_id="BR-01")
    action = recommend(confidence, branch_id="BR-01")
    if confidence.confidence_band in ("LOW", "ABSTAIN"):
        assert action is not None and action.driver_key == "abstain"
