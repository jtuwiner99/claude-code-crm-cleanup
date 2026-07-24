import csv
import os
from crm_report_card.export_lists import write_lists


def _records():
    return [
        {"record_id": "1", "company_name": "Acme", "domain": "acme.com"},
        {"record_id": "2", "company_name": "Acme Inc", "domain": "acme.com"},
        {"record_id": "3", "company_name": "Globex", "domain": "globex.io"},
    ]


def _metrics():
    return {
        "facts": {
            "duplicates": {
                "duplicate_rate": 0.33,
                "grade": "F",
                "offending_ids": ["1", "2"],
                "examples": [{"record_id": "1", "label": "acme.com", "detail": "shares domain acme.com"}],
            },
            "junk": {
                "junk_rate": 0.0,
                "grade": "A",
                "offending_ids": [],
                "examples": [],
            },
        }
    }


def test_write_lists_writes_offending_rows_with_flag_reason(tmp_path):
    out_dir = str(tmp_path / "lists")
    result = write_lists("company", _metrics(), _records(), out_dir)

    assert result == {"duplicates": "company-duplicates.csv"}

    path = os.path.join(out_dir, "company-duplicates.csv")
    assert os.path.exists(path)

    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    assert "flag_reason" in rows[0]
    assert len(rows) == 2
    assert {r["record_id"] for r in rows} == {"1", "2"}
    # exactly the offending rows: the untouched Globex row must not appear
    assert "Globex" not in [r.get("company_name") for r in rows]

    by_id = {r["record_id"]: r for r in rows}
    assert by_id["1"]["flag_reason"] == "shares domain acme.com"
    assert by_id["2"]["flag_reason"] == "duplicates"  # no example detail -> falls back to signal name


def test_write_lists_skips_facts_with_no_offending_ids(tmp_path):
    out_dir = str(tmp_path / "lists")
    result = write_lists("company", _metrics(), _records(), out_dir)
    assert "junk" not in result
    assert not os.path.exists(os.path.join(out_dir, "company-junk.csv"))


def test_write_lists_creates_out_dir(tmp_path):
    out_dir = str(tmp_path / "nested" / "lists")
    assert not os.path.exists(out_dir)
    write_lists("company", _metrics(), _records(), out_dir)
    assert os.path.exists(out_dir)
