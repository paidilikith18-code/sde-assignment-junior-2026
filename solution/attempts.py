from solution.database import get_connection


def record_accepted_call(request_id, call_sid=None):
    """
    Count an accepted provider call exactly once.

    This function is safe to call from:
    - A successful HTTP response
    - Crash recovery
    - Webhook processing
    """

    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")

        call = connection.execute(
            "SELECT * FROM calls WHERE request_id = ?",
            (request_id,),
        ).fetchone()

        if call is None:
            raise ValueError("Unknown request_id")

        if call["attempt_counted"]:
            return "already_counted"

        connection.execute(
            """
            UPDATE calls
            SET attempt_counted = 1,
                call_sid = COALESCE(call_sid, ?)
            WHERE request_id = ?
            """,
            (call_sid, request_id),
        )

        connection.execute(
            """
            UPDATE leads
            SET attempts = attempts + 1
            WHERE campaign_id = ? AND lead_id = ?
            """,
            (call["campaign_id"], call["lead_id"]),
        )

        return "counted"
