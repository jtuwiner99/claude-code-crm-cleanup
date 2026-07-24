from crm_report_card.grading import grade_rate, overall_grade


def test_grade_rate_thresholds():
    assert grade_rate(0.0) == "A"
    assert grade_rate(0.02) == "B"
    assert grade_rate(0.05) == "C"
    assert grade_rate(0.10) == "D"
    assert grade_rate(0.40) == "F"


def test_overall_grade_average():
    assert overall_grade(["A", "A", "B"]) == "A"
    assert overall_grade(["D", "F", "F"]) == "F"
    assert overall_grade([]) == "N/A"


def test_overall_grade_single_f_caps_at_d():
    assert overall_grade(["A", "A", "F"]) == "D"


def test_overall_grade_all_f_stays_f():
    assert overall_grade(["F", "F", "F"]) == "F"


def test_overall_grade_no_f_unchanged():
    assert overall_grade(["A", "A", "B"]) == "A"
