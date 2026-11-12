import csv
from pathlib import Path

from solution.database import get_connection


def export_final_states(output_path="solution/final_state.csv"):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with get_connection() as db:
        rows = db.execute("""
            SELECT
                campaign_id,
                lead_id,
                state AS final_state,
                attempts,
                last_status,
                last_disposition
            FROM leads
            ORDER BY campaign_id, lead_id
        """).fetchall()

    pending = [
        row for row in rows
        if row["final_state"] not in (
            "completed", "exhausted", "dnd_blocked"
        )
    ]

    if pending:
        raise RuntimeError(
            f"Cannot export: {len(pending)} leads are not finalized"
        )

    fields = [
        "campaign_id",
        "lead_id",
        "final_state",
        "attempts",
        "last_status",
        "last_disposition",
    ]

    with output_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()

        for row in rows:
            writer.writerow(dict(row))

    print(f"Exported {len(rows)} leads to {output_path}")


if __name__ == "__main__":
    export_final_states()
