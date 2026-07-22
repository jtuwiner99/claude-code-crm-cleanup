from crm_report_card.grading import grade_rate, overall_grade


def test_grade_rate_thresholds():
    assert grade_rate(0.0) == "A"
    assert grade_rate(0.03) == "B"
    assert grade_rate(0.08) == "C"
    assert grade_rate(0.15) == "D"
    assert grade_rate(0.40) == "F"


def test_overall_grade_average():
    assert overall_grade(["A", "A", "B"]) == "A"
    assert overall_grade(["D", "F", "F"]) == "F"
    assert overall_grade([]) == "N/A"
