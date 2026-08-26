import pathlib
import sys
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from analytics.kpi_calculator import latest_kpi_result  # noqa: E402
from analytics.detect import detect, _materiality_band  # noqa: E402

DB_PATH = ROOT / "db" / "banking.db"


def _db_ready():
    return DB_PATH.exists()


@pytest.mark.skipif(not _db_ready(), reason="db/banking.db not initialized — run setup scripts first")
def test_detect_returns_result_for_cross_sell_revenue():
    kpi = latest_kpi_result("cross_sell_revenue", branch_id="BR-01")
    result = detect(kpi)
    assert result.kpi.kpi_key == "cross_sell_revenue"
    assert result.materiality_band in ("negligible", "low", "medium", "high")
    assert isinstance(result.is_anomalous, bool)


def test_materiality_band_thresholds():
    assert _materiality_band(0.01) == "negligible"
    assert _materiality_band(0.06) == "low"
    assert _materiality_band(0.12) == "medium"
    assert _materiality_band(0.25) == "high"
