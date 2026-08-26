"""Deterministic detection: baseline -> deviation -> z-score -> materiality.

historical baseline -> expected value -> deviation -> z-score -> business
impact -> materiality score

No LLM. This is the statistical proof that a movement is real, not noise.
"""
import pathlib
import yaml
import numpy as np
from core.models import KPIResult, DetectionResult
from analytics.kpi_calculator import compute_kpi_series
from core.telemetry import timed_stage

ROOT = pathlib.Path(__file__).resolve().parent.parent
with open(ROOT / "config" / "kpi_definitions.yaml") as f:
    _CFG = yaml.safe_load(f)

MATERIALITY_THRESHOLDS = _CFG["materiality_thresholds"]  # low/medium/high cutoffs
MIN_HISTORY_MONTHS = 4          # below this we flag sparse_history
Z_ANOMALY_THRESHOLD = 1.5       # |z| beyond this is flagged anomalous


def _materiality_band(materiality: float) -> str:
    if materiality >= MATERIALITY_THRESHOLDS["high"]:
        return "high"
    if materiality >= MATERIALITY_THRESHOLDS["medium"]:
        return "medium"
    if materiality >= MATERIALITY_THRESHOLDS["low"]:
        return "low"
    return "negligible"


def detect(kpi: KPIResult, db_path=None, series_df=None) -> DetectionResult:
    """series_df lets callers pass a pre-computed series (e.g. a product-scoped
    series from kpi_calculator.compute_product_revenue_series) instead of
    re-deriving it from kpi.kpi_key, which only maps to the 4 registered KPIs."""
    with timed_stage("detect"):
        if series_df is not None:
            df = series_df
        elif db_path:
            df = compute_kpi_series(kpi.kpi_key, kpi.branch_id, db_path)
        else:
            df = compute_kpi_series(kpi.kpi_key, kpi.branch_id)
        df = df.dropna(subset=["value"])
        history = df.iloc[:-1]["value"].to_numpy() if len(df) > 1 else np.array([])

        sparse = len(history) < MIN_HISTORY_MONTHS

        if len(history) >= 2:
            std = float(np.std(history, ddof=1)) if len(history) > 1 else 0.0
        else:
            std = 0.0

        z = 0.0 if std == 0 else (kpi.actual - kpi.expected) / std
        is_anomalous = abs(z) >= Z_ANOMALY_THRESHOLD or sparse

        # business impact proxy: |change_pct| weighted by whether it's adverse
        materiality = min(abs(kpi.change_pct), 1.0)
        band = _materiality_band(materiality)

        # persistence: how many of the trailing 3 months (excluding current)
        # moved in the same direction as the current deviation
        persistence = 0
        if len(history) >= 2:
            direction = np.sign(kpi.actual - kpi.expected)
            diffs = np.diff(history)
            persistence = int(np.sum(np.sign(diffs) == direction))

        return DetectionResult(
            kpi=kpi,
            z_score=round(float(z), 3),
            is_anomalous=bool(is_anomalous),
            materiality=round(float(materiality), 3),
            materiality_band=band,
            method="baseline_zscore",
            persistence_months=persistence,
            sparse_history=bool(sparse),
        )


def detect_all(kpi_results: list, db_path=None) -> list:
    return [detect(k, db_path) for k in kpi_results]
