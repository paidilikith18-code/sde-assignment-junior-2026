import csv
from pathlib import Path


CSV_PATH = Path("solution/final_state.csv")

REQUIRED_COLUMNS = [
    "campaign_id",
    "lead_id",
    "final_state",
    "attempts",
    "last_status",
    "last_disposition",
]


def load_rows():
    with CSV_PATH.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == REQUIRED_COLUMNS
        return list(reader)


def test_export_has_200_leads():
    assert len(load_rows()) == 200


def test_export_has_unique_leads():
    rows = load_rows()
    keys = [(r["campaign_id"], r["lead_id"]) for r in rows]
    assert len(keys) == len(set(keys))


def test_export_is_sorted():
    rows = load_rows()
    keys = [(r["campaign_id"], r["lead_id"]) for r in rows]
    assert keys == sorted(keys)


def test_all_leads_are_finalized():
    valid_states = {
        "completed",
        "exhausted",
        "dnd_blocked",
    }

    for row in load_rows():
        assert row["final_state"] in valid_states


def test_attempt_limit():
    for row in load_rows():
        attempts = int(row["attempts"])
        assert 0 <= attempts <= 3
