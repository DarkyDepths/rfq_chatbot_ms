"""Phase 5 Mode A closed-list capability status mapping."""

from __future__ import annotations

from typing import TypedDict


class CapabilityStatus(TypedDict):
    capability_name: str
    named_future_condition: str


CAPABILITY_STATUS_ENTRIES: dict[str, CapabilityStatus] = {
    "briefing": {
        "capability_name": "RFQ intelligence briefing retrieval",
        "named_future_condition": "available after briefing rollout is enabled in a later phase",
    },
    "workbook review": {
        "capability_name": "Workbook review extraction",
        "named_future_condition": "available after workbook-review integration is enabled in a later phase",
    },
    "workbook profile": {
        "capability_name": "Workbook profile extraction",
        "named_future_condition": "available after workbook-profile integration is enabled in a later phase",
    },
    "analytics": {
        "capability_name": "Portfolio analytics retrieval",
        "named_future_condition": "available after portfolio analytics support is enabled in a later phase",
    },
    "stats": {
        "capability_name": "Portfolio KPI statistics retrieval",
        "named_future_condition": "available after portfolio statistics support is enabled in a later phase",
    },
    "list rfqs": {
        "capability_name": "Portfolio RFQ listing",
        "named_future_condition": "available after portfolio listing support is enabled in a later phase",
    },
    "portfolio": {
        "capability_name": "Portfolio-level RFQ analysis",
        "named_future_condition": "available after portfolio mode retrieval support is enabled in a later phase",
    },
    "grand total": {
        "capability_name": "Workbook grand total value retrieval",
        "named_future_condition": "available after workbook financial extraction support is enabled",
    },
    "final price": {
        "capability_name": "Workbook final price retrieval",
        "named_future_condition": "available after workbook financial extraction support is enabled",
    },
    "estimation amount": {
        "capability_name": "Estimation amount retrieval",
        "named_future_condition": "available after estimation-field extraction support is enabled",
    },
    "historical comparison": {
        "capability_name": "Historical RFQ comparison benchmarking",
        "named_future_condition": (
            "available after outcomes are recorded across multiple comparable RFQs"
        ),
    },
    "similar rfq": {
        "capability_name": "Similar RFQ retrieval",
        "named_future_condition": (
            "available after similarity indexing is enabled over a larger RFQ corpus"
        ),
    },
    "supplier recommendation": {
        "capability_name": "Supplier recommendation support",
        "named_future_condition": (
            "available after supplier performance history is integrated and validated"
        ),
    },
    "material pricing": {
        "capability_name": "Material pricing intelligence",
        "named_future_condition": (
            "available after material pricing feeds are integrated and quality-checked"
        ),
    },
}
