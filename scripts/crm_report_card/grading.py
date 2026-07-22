"""Map bad-rates to letter grades and compute an overall grade."""
from __future__ import annotations

_POINTS = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
_LETTERS = ["A", "B", "C", "D", "F"]


def grade_rate(bad_rate: float) -> str:
    if bad_rate < 0.02:
        return "A"
    if bad_rate < 0.05:
        return "B"
    if bad_rate < 0.10:
        return "C"
    if bad_rate < 0.20:
        return "D"
    return "F"


def overall_grade(grades: list[str]) -> str:
    if not grades:
        return "N/A"
    avg = sum(_POINTS[g] for g in grades) / len(grades)
    if avg >= 3.5:
        return "A"
    if avg >= 2.5:
        return "B"
    if avg >= 1.5:
        return "C"
    if avg >= 0.5:
        return "D"
    return "F"
