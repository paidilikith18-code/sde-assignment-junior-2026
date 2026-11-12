from solution.database import get_connection


def handle_call_response(request_id, status_code, response_data=None):
    """
    Persist the provider response for an existing call reservation.

    This function does not make an HTTP request.
    """
    response_data = response_data or {}

    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")

        call = connection.execute(
            "SELECT * FROM calls WHERE request_id = ?",
            (request_id,),
        ).fetchone()

        if call is None:
            raise ValueError("Unknown request_id")

        # A webhook may have completed this call before the HTTP
        # response arrived. Never overwrite that final result.
        if call["state"] == "ended":
            return "already_ended"

        if status_code in (200, 201):
            call_sid = response_data.get("call_sid")

            if not call_sid:
                raise ValueError("Accepted response missing call_sid")

            connection.execute(
                """
                UPDATE calls
                SET call_sid = ?, state = 'active'
                WHERE request_id = ?
                """,
                (call_sid, request_id),
            )

            return "accepted"

        if status_code == 503:
            connection.execute(
                """
                UPDATE calls
                SET state = 'not_placed'
                WHERE request_id = ?
                """,
                (request_id,),
            )

            return "not_placed"

        if status_code == 504:
            connection.execute(
                """
                UPDATE calls
                SET state = 'uncertain'
                WHERE request_id = ?
                """,
                (request_id,),
            )

            return "reconcile"

        if status_code in (429, 409, 422):
            connection.execute(
                """
                UPDATE calls
                SET state = 'uncertain'
                WHERE request_id = ?
                """,
                (request_id,),
            )

            return "provider_violation"

        return "unexpected_response"
