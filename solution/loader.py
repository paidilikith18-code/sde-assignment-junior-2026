import csv

from solution.config import FIXTURES_DIR, load_config
from solution.database import get_connection, initialize_database


def load_leads():
    initialize_database()
    config = load_config()
    inserted = 0

    with get_connection() as connection:
        for campaign in config["campaigns"]:
            campaign_id = campaign["campaign_id"]
            tenant_id = campaign["tenant_id"]
            csv_path = FIXTURES_DIR / campaign["leads_file"]

            with open(csv_path, "r", encoding="utf-8", newline="") as file:
                reader = csv.DictReader(file)

                for lead in reader:
                    cursor = connection.execute(
                        """
                        INSERT OR IGNORE INTO leads (
                            campaign_id,
                            lead_id,
                            tenant_id,
                            phone,
                            customer_name
                        )
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            campaign_id,
                            lead["lead_id"],
                            tenant_id,
                            lead["phone"],
                            lead["customer_name"],
                        ),
                    )
                    inserted += cursor.rowcount

    return inserted


if __name__ == "__main__":
    count = load_leads()
    print(f"New leads inserted: {count}")
