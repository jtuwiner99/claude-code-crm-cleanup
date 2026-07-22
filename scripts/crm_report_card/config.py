"""Run-config schema and loader for a CRM Report Card run."""
from __future__ import annotations
import json
from dataclasses import dataclass, field

DEFAULT_PRODUCT_NAME = "The CRM Report Card"
_REQUIRED = ("icp_nl", "critical_properties", "field_mapping", "contact_email", "booking_url")


@dataclass
class RunConfig:
    icp_nl: str
    critical_properties: list[str]
    field_mapping: dict[str, str]
    contact_email: str
    booking_url: str
    favorite_customers: list[str] = field(default_factory=list)
    product_name: str = DEFAULT_PRODUCT_NAME


def load_config(path: str) -> RunConfig:
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    for key in _REQUIRED:
        if key not in raw:
            raise ValueError(f"run-config missing required key: {key}")
    if not str(raw["icp_nl"]).strip():
        raise ValueError("run-config icp_nl must not be empty")
    return RunConfig(
        icp_nl=raw["icp_nl"],
        critical_properties=list(raw["critical_properties"]),
        field_mapping=dict(raw["field_mapping"]),
        contact_email=raw["contact_email"],
        booking_url=raw["booking_url"],
        favorite_customers=list(raw.get("favorite_customers", [])),
        product_name=raw.get("product_name") or DEFAULT_PRODUCT_NAME,
    )
