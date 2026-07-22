from crm_report_card.field_mapping import auto_map, resolve_mapping, CANONICAL_ROLES


def test_auto_map_common_headers():
    m = auto_map(["Company", "Website", "Email", "Employees", "Last Activity", "record_id", "Contact"])
    assert m["company_name"] == "Company"
    assert m["domain"] == "Website"
    assert m["email"] == "Email"
    assert m["company_size"] == "Employees"
    assert m["last_activity"] == "Last Activity"
    assert m["record_id"] == "record_id"
    assert m["contact_name"] == "Contact"


def test_auto_map_omits_unknown_roles():
    m = auto_map(["RandomColA", "RandomColB"])
    assert m == {}


def test_resolve_mapping_applies_valid_overrides_only():
    headers = ["Org", "Domain", "Email"]
    m = resolve_mapping(headers, {"company_name": "Org", "domain": "NotTHere"})
    assert m["company_name"] == "Org"
    assert m["email"] == "Email"        # from auto_map
    assert "domain" not in m or m["domain"] == "Domain"  # bad override ignored, auto_map kept


def test_canonical_roles_shape():
    assert "company_name" in CANONICAL_ROLES and "domain" in CANONICAL_ROLES
