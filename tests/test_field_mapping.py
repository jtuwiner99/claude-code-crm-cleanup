from crm_report_card.field_mapping import (auto_map, resolve_mapping, roles_for,
                                           hubspot_internal, CANONICAL_ROLES)


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
                               "company_size", "last_activity", "record_id",
                               "first_name", "last_name", "associated_company_id")


def test_associated_company_id_maps_without_stealing_record_id():
    headers = ["Record ID", "Associated Company ID", "Email"]
    m = auto_map(headers, object_type="contact")
    assert m["record_id"] == "Record ID"
    assert m["associated_company_id"] == "Associated Company ID"


def test_contacts_map_domain_to_email_domain_not_website():
    """Contacts key their domain off Email Domain, never a website column.

    On a real 848-contact book, Website URL was 20.8% filled and Email Domain
    97.3%, the same information with four times the coverage.
    """
    headers = ["Email", "Email Domain", "Website URL"]
    m = auto_map(headers, object_type="contact")
    assert m["domain"] == "Email Domain"


def test_contacts_leave_domain_unmapped_when_only_a_website_column_exists():
    # Better unmapped (the loader then derives it from the email address) than
    # graded off a personal website field.
    m = auto_map(["Email", "Website URL"], object_type="contact")
    assert "domain" not in m


def test_companies_still_map_domain_from_the_company_domain_column():
    m = auto_map(["Company Domain Name", "Email Domain"], object_type="company")
    assert m["domain"] == "Company Domain Name"


def test_company_size_is_never_mapped_on_contacts():
    """Company size is a company property; on contacts it was 0.2% filled."""
    m = auto_map(["Email", "Company size", "Number of Employees"], object_type="contact")
    assert "company_size" not in m


def test_associated_company_id_is_not_mapped_on_companies():
    m = auto_map(["Company name", "Associated Company ID"], object_type="company")
    assert "associated_company_id" not in m


def test_override_cannot_reintroduce_company_size_on_contacts():
    # A stale run-config must not silently re-map a company property onto the
    # contact object.
    m = resolve_mapping(["Email", "Company size"], {"company_size": "Company size"},
                        object_type="contact")
    assert "company_size" not in m


def test_roles_for_object_type():
    assert "company_size" not in roles_for("contact")
    assert "associated_company_id" in roles_for("contact")
    assert "company_size" in roles_for("company")
    assert "associated_company_id" not in roles_for("company")


def test_hubspot_internal_is_object_aware():
    assert hubspot_internal("domain", "contact") == "hs_email_domain"
    assert hubspot_internal("domain", "company") == "domain"
    assert hubspot_internal("company_name", "contact") == "company"
    assert hubspot_internal("associated_company_id", "contact") == "associatedcompanyid"


def test_auto_map_first_and_last_name():
    m = auto_map(["First Name", "Last Name", "Email"])
    assert m["first_name"] == "First Name"
    assert m["last_name"] == "Last Name"
    assert m["email"] == "Email"
