from crm_report_card.field_mapping import auto_map, resolve_mapping, CANONICAL_ROLES


def test_auto_map_hubspot_defaults():
    m = auto_map(["Company name", "Company Domain Name", "Number of Employees",
                  "Last Activity Date"])
    assert m["company_name"] == "Company name"
    assert m["domain"] == "Company Domain Name"
    assert m["company_size"] == "Number of Employees"
    assert m["last_activity"] == "Last Activity Date"
    assert "contact_name" not in m
    assert "email" not in m


def test_auto_map_does_not_misassign_contact_name_or_email():
    # Regression: greedy substring matching used to grab "Company Domain Name"
    # for contact_name and a date column for email. Exact-alias matching must
    # leave both roles unmapped when there's no real header for them.
    headers = ["Company name", "Company Domain Name",
               "Last Logged Outgoing Email Date", "Number of Employees"]
    m = auto_map(headers)
    assert "contact_name" not in m
    assert "email" not in m


def test_auto_map_omits_unknown_roles():
    m = auto_map(["RandomColA", "RandomColB"])
    assert m == {}


def test_resolve_mapping_applies_valid_overrides_and_ignores_missing_headers():
    headers = ["Org", "Domain", "Email"]
    m = resolve_mapping(headers, {"company_name": "Org", "domain": "NotThere"})
    assert m["company_name"] == "Org"          # valid override applied
    assert m["email"] == "Email"                # from auto_map, untouched
    assert m["domain"] == "Domain"              # invalid override ignored, auto_map kept


def test_canonical_roles_shape():
    assert CANONICAL_ROLES == ("company_name", "domain", "contact_name", "email",
                               "company_size", "last_activity", "record_id")
