from src.config.capability_status import CAPABILITY_STATUS_ENTRIES


def test_capability_status_entries_keys_match_phase4_unsupported_keywords():
    assert set(CAPABILITY_STATUS_ENTRIES) == {
        "briefing",
        "workbook review",
        "workbook profile",
        "analytics",
        "stats",
        "list rfqs",
        "portfolio",
        "grand total",
        "final price",
        "estimation amount",
        "historical comparison",
        "similar rfq",
        "supplier recommendation",
        "material pricing",
    }


def test_capability_status_entries_have_non_empty_metadata():
    for entry in CAPABILITY_STATUS_ENTRIES.values():
        assert entry["capability_name"].strip()
        assert entry["named_future_condition"].strip()
