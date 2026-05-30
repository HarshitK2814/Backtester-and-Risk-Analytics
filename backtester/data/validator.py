from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Optional
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)
REQUIRED_COLUMNS = {"timestamp", "open", "high", "low", "close", "volume"}

@dataclass
class ValidationResult:
    quality_score: float = 100.0
    issues:   list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stats:    dict       = field(default_factory=dict)
    passed:   bool       = True

    def add_issue(self, msg, deduction=5.0):
        self.issues.append(msg)
        self.quality_score = max(0.0, self.quality_score - deduction)
        self.passed = self.quality_score >= 50.0

    def add_warning(self, msg, deduction=2.0):
        self.warnings.append(msg)
        self.quality_score = max(0.0, self.quality_score - deduction)


class DataValidator:
    def __init__(self, outlier_z_threshold=5.0, max_gap_multiplier=3.0):
        self.outlier_z_threshold = outlier_z_threshold
        self.max_gap_multiplier  = max_gap_multiplier

    def validate(self, df: pd.DataFrame, interval="1d") -> ValidationResult:
        result = ValidationResult()
        self._check_schema(df, result)
        if result.quality_score < 50: return result
        self._check_types(df, result)
        self._check_ranges(df, result)
        self._check_duplicates(df, result)
        self._check_continuity(df, result, interval)
        self._check_outliers(df, result)
        self._check_nan_inf(df, result)
        self._collect_stats(df, result)
        result.passed = result.quality_score >= 50.0
        return result

    def _check_schema(self, df, result):
        missing = REQUIRED_COLUMNS - set(df.columns)
        if missing: result.add_issue(f"Missing columns: {missing}", 30.0)

    def _check_types(self, df, result):
        for col in ["open","high","low","close","volume"]:
            if col in df.columns and not pd.api.types.is_numeric_dtype(df[col]):
                result.add_issue(f"'{col}' not numeric", 10.0)

    def _check_ranges(self, df, result):
        for col in ["open","high","low","close"]:
            if col in df.columns:
                bad = (df[col] <= 0).sum()
                if bad: result.add_issue(f"{bad} non-positive in '{col}'", 10.0)
        if "volume" in df.columns:
            bad = (df["volume"] < 0).sum()
            if bad: result.add_issue(f"{bad} negative volume", 5.0)
        if {"high","low"}.issubset(df.columns):
            bad = (df["high"] < df["low"]).sum()
            if bad: result.add_issue(f"{bad} rows where high < low", 10.0)

    def _check_duplicates(self, df, result):
        if "timestamp" in df.columns:
            dups = df.duplicated("timestamp").sum()
            if dups: result.add_issue(f"{dups} duplicate timestamps", 5.0)

    def _check_continuity(self, df, result, interval):
        if "timestamp" not in df.columns or len(df) < 2: return
        ts = pd.to_datetime(df["timestamp"]).sort_values().reset_index(drop=True)
        diffs = ts.diff().dropna()
        median_diff = diffs.median()
        gaps = diffs[diffs > median_diff * self.max_gap_multiplier]
        if len(gaps):
            pct = len(gaps) / len(df) * 100
            result.add_warning(f"{len(gaps)} gaps > {self.max_gap_multiplier}x median ({pct:.1f}%)", min(20.0, pct*2))

    def _check_outliers(self, df, result):
        if "close" not in df.columns or len(df) < 5: return
        returns = df["close"].pct_change().dropna()
        mean_r, std_r = returns.mean(), returns.std()
        if std_r < 1e-10: return
        outliers = ((returns - mean_r).abs() / std_r > self.outlier_z_threshold).sum()
        if outliers: result.add_warning(f"{outliers} extreme returns (Z>{self.outlier_z_threshold:.0f})", min(10.0, outliers*2))

    def _check_nan_inf(self, df, result):
        for col in ["open","high","low","close","volume"]:
            if col not in df.columns: continue
            nan_cnt = df[col].isna().sum()
            if nan_cnt: result.add_issue(f"{nan_cnt} NaN in '{col}'", 5.0)

    def _collect_stats(self, df, result):
        result.stats = {
            "total_rows": len(df),
            "date_range": {"start": str(df["timestamp"].min()) if "timestamp" in df.columns else None,
                          "end":   str(df["timestamp"].max()) if "timestamp" in df.columns else None},
            "close_mean": float(df["close"].mean()) if "close" in df.columns else None,
            "close_min":  float(df["close"].min())  if "close" in df.columns else None,
            "close_max":  float(df["close"].max())  if "close" in df.columns else None,
        }
