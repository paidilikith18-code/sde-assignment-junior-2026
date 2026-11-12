import httpx

from solution.database import get_connection
from solution.provider import TelephonyClient
from solution.result_processor import process_call_result


def reconcile_call(request_id, client):
    """
    Recover an unfinished call using its original request_id.

    Never generates a new request_id.
    """

    with get_connection() as connection:
        call = connection.execute(
            "SELECT * FROM calls WHERE request_id = ?",
            (request_id,),
        ).fetchone()

    if call is None:
        raise ValueError("Unknown request_id")

    if call["state"] in ("ended", "not_placed"):
        return "already_resolved"

    try:
        provider_call = client.find_call(request_id)

    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return "not_found"
        return "lookup_failed"

    except (httpx.RequestError, ValueError):
        return "lookup_failed"

    if not isinstance(provider_call, dict):
        return "unexpected_response"

    if provider_call.get("request_id") != request_id:
        return "unexpected_response"

    if (
        provider_call.get("campaign_id") != call["campaign_id"]
        or provider_call.get("lead_id") != call["lead_id"]
    ):
        return "identity_mismatch"

    call_sid = provider_call.get("call_sid")
    if not call_sid:
        return "unexpected_response"

    if provider_call.get("state") == "ended":
        result = provider_call.get("result")

        if not isinstance(result, dict):
            return "missing_result"

        if (
            result.get("request_id") != request_id
            or result.get("call_sid") != call_sid
        ):
            return "identity_mismatch"

        process_call_result(result)
        return "recovered_ended"

    if provider_call.get("state") != "active":
        return "unexpected_state"

    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")

        current = connection.execute(
            "SELECT state FROM calls WHERE request_id = ?",
            (request_id,),
        ).fetchone()

        if current["state"] == "ended":
            return "already_resolved"

        connection.execute(
            """
            UPDATE calls
            SET call_sid = ?,
                state = 'active'
            WHERE request_id = ?
            """,
            (call_sid, request_id),
        )

    return "recovered_active"
