import pathlib
import sys
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from analytics.kpi_calculator import latest_kpi_result  # noqa: E402
from analytics.detect import detect  # noqa: E402
from analytics.attribute import attribute_by_product, attribute_volume_mix_price  # noqa: E402

DB_PATH = ROOT / "db" / "banking.db"


@pytest.mark.skipif(not DB_PATH.exists(), reason="db/banking.db not initialized — run setup scripts first")
def test_attribute_by_product_contributions_are_directional():
    kpi = latest_kpi_result("cross_sell_revenue", branch_id="BR-01")
    detection = detect(kpi)
    attribution = attribute_by_product(detection)
    assert attribution.method == "product_contribution"
    if attribution.drivers:
        # top driver should have the largest |contribution|
        top = attribution.drivers[0]
        assert all(abs(top.contribution_pct) >= abs(d.contribution_pct) for d in attribution.drivers)


@pytest.mark.skipif(not DB_PATH.exists(), reason="db/banking.db not initialized — run setup scripts first")
def test_volume_mix_price_bridge_sums_to_total():
    kpi = latest_kpi_result("cross_sell_revenue", branch_id="BR-01")
    detection = detect(kpi)
    attribution = attribute_volume_mix_price(detection)
    if attribution.drivers:
        total_pct = sum(d.contribution_pct for d in attribution.drivers)
        assert abs(total_pct - 1.0) < 0.01  # volume + mix + price should reconstruct 100% of delta
