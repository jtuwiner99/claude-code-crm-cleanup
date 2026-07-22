"""Validate + merge the single-pass AI 'qualified %' ESTIMATE block.

verified is ALWAYS False: this block is an unverified, single-pass guess.
"""
from __future__ import annotations
import copy


def validate_ai_baseline(raw: dict) -> dict:
    est = raw.get("qualified_estimate")
    if not isinstance(est, (int, float)) or not (0.0 <= float(est) <= 1.0):
        raise ValueError("qualified_estimate must be a float in [0, 1]")
    reasons = raw.get("reasons")
    if not isinstance(reasons, list) or not reasons or not all(isinstance(r, str) for r in reasons):
        raise ValueError("reasons must be a non-empty list of strings")
    sample = raw.get("sample_size")
    if not isinstance(sample, int) or sample < 0:
        raise ValueError("sample_size must be a non-negative int")
    return {
        "qualified_estimate": float(est),
        "reasons": list(reasons),
        "sample_size": sample,
        "verified": False,
    }


def merge_ai_baseline(metrics: dict, raw: dict) -> dict:
    out = copy.deepcopy(metrics)
    out["ai_baseline"] = validate_ai_baseline(raw)
    return out
