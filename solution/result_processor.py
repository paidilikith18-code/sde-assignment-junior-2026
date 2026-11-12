from solution.database import get_connection
from solution.scheduler import next_eligible_time
from solution.config import load_config
from solution.attempts import record_accepted_call


TERMINAL = {
    "interested",
    "not_interested",
    "wrong_number",
    "dnd",
}


def process_call_result(payload):
    request_id = payload["request_id"]
    status = payload["status"]
    disposition = payload.get("disposition")
    ended_at = payload["ended_at"]

    if not ended_at:
        raise ValueError("Missing ended_at")

    config = load_config()

    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")

        call = connection.execute(
            """
            SELECT *
            FROM calls
            WHERE request_id = ?
            """,
            (request_id,),
        ).fetchone()

        if call is None:
            raise ValueError("Unknown request_id")

        if call["state"] == "ended":
            return "duplicate_ignored"

        # Prevent a result from being applied to the wrong call.
        if payload.get("call_sid") and call["call_sid"]:
            if payload["call_sid"] != call["call_sid"]:
                raise ValueError("Call SID mismatch")

        for field in ("campaign_id", "lead_id", "phone"):
            if field in payload and payload[field] != call[field]:
                raise ValueError(f"{field} mismatch")

        lead = connection.execute(
            """
            SELECT *
            FROM leads
            WHERE campaign_id = ?
            AND lead_id = ?
            """,
            (call["campaign_id"], call["lead_id"]),
        ).fetchone()

        if lead is None:
            raise ValueError("Unknown lead")

        campaign = next(
            (
                campaign
                for campaign in config["campaigns"]
                if campaign["campaign_id"] == call["campaign_id"]
            ),
            None,
        )

        if campaign is None:
            raise ValueError("Unknown campaign")

        # Count this accepted call within the SAME SQLite transaction.
        # This avoids nested write transactions and database lock errors.
        if not call["attempt_counted"]:
            connection.execute(
                """
                UPDATE calls
                SET attempt_counted = 1
                WHERE request_id = ?
                """,
                (request_id,),
            )

            connection.execute(
                """
                UPDATE leads
                SET attempts = attempts + 1
                WHERE campaign_id = ?
                AND lead_id = ?
                """,
                (call["campaign_id"], call["lead_id"]),
            )

        # Read the updated attempt count.
        lead = connection.execute(
            """
            SELECT *
            FROM leads
            WHERE campaign_id = ?
            AND lead_id = ?
            """,
            (call["campaign_id"], call["lead_id"]),
        ).fetchone()

        attempts = lead["attempts"]

        # Store the completed call.
        connection.execute(
            """
            UPDATE calls
            SET state = 'ended',
                call_sid = COALESCE(call_sid, ?),
                status = ?,
                disposition = ?,
                started_at = COALESCE(started_at, ?),
                ended_at = ?
            WHERE request_id = ?
            """,
            (
                payload.get("call_sid"),
                status,
                disposition,
                payload.get("started_at"),
                ended_at,
                request_id,
            ),
        )

        # Preserve already-finalized lead states.
        if lead["state"] in (
            "completed",
            "exhausted",
            "dnd_blocked",
        ):
            final_state = lead["state"]
            next_time = None

        elif disposition in TERMINAL:
            final_state = "completed"
            next_time = None

        elif attempts >= campaign["max_attempts"]:
            final_state = "exhausted"
            next_time = None

        else:
            next_time = next_eligible_time(
                status,
                disposition,
                ended_at,
                payload.get("callback_at"),
            )

            if next_time is None:
                raise ValueError(
                    "No retry or callback time for nonterminal result"
                )

            final_state = "pending"

        connection.execute(
            """
            UPDATE leads
            SET state = ?,
                next_eligible_at = ?,
                last_status = ?,
                last_disposition = ?
            WHERE campaign_id = ?
            AND lead_id = ?
            """,
            (
                final_state,
                next_time.isoformat() if next_time else None,
                status,
                disposition,
                call["campaign_id"],
                call["lead_id"],
            ),
        )

        # Apply global DND across all campaigns.
        if disposition == "dnd":
            connection.execute(
                """
                INSERT OR IGNORE INTO dnd_phones(phone)
                VALUES (?)
                """,
                (call["phone"],),
            )

            connection.execute(
                """
                UPDATE leads
                SET state = 'dnd_blocked',
                    next_eligible_at = NULL
                WHERE phone = ?
                AND state = 'pending'
                """,
                (call["phone"],),
            )

        return final_state