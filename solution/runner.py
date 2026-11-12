import logging
import time
from datetime import datetime, timedelta

import httpx

from solution.attempts import record_accepted_call
from solution.call_handler import handle_call_response
from solution.config import load_config
from solution.database import get_connection, initialize_database
from solution.dispatcher import reserve_call_safely
from solution.loader import load_leads
from solution.provider import TelephonyClient
from solution.recovery import reconcile_call

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

CALLBACK_URL = "http://127.0.0.1:8200/webhooks/telephony"

UNFINISHED = ("prepared", "sending", "active", "uncertain")


_clock_sync = None

def get_simulated_now(client):
    global _clock_sync

    current_real_time = time.time()

    # Refresh synchronization periodically.
    if (
        _clock_sync is None
        or current_real_time - _clock_sync["synced_at"] >= 2
    ):
        clock = client.get_clock()

        _clock_sync = {
            "sim_epoch": datetime.fromisoformat(
                clock["sim_epoch"]
            ),
            "real_epoch": float(clock["real_epoch"]),
            "speed": float(clock["speed"]),
            "synced_at": time.time(),
        }

    elapsed_real_seconds = (
        time.time() - _clock_sync["real_epoch"]
    )

    return _clock_sync["sim_epoch"] + timedelta(
        seconds=elapsed_real_seconds * _clock_sync["speed"]
    )


def get_unfinished_calls():
    with get_connection() as connection:
        return [
            dict(row)
            for row in connection.execute(
                """
                SELECT *
                FROM calls
                WHERE state IN ('prepared', 'sending', 'active', 'uncertain')
                ORDER BY rowid
                """
            )
        ]


def get_candidates():
    """
    Priority:
    0 = due callback
    1 = retry
    2 = fresh lead
    """
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM leads
            WHERE state = 'pending'
            ORDER BY
                CASE
                    WHEN last_disposition = 'callback_requested' THEN 0
                    WHEN attempts > 0 THEN 1
                    ELSE 2
                END,
                COALESCE(next_eligible_at, ''),
                campaign_id,
                lead_id
            """
        ).fetchall()

    return [dict(row) for row in rows]


def send_reserved_call(client, call):
    request_id = call["request_id"]

    payload = {
        "request_id": request_id,
        "campaign_id": call["campaign_id"],
        "lead_id": call["lead_id"],
        "phone": call["phone"],
        "callback_url": CALLBACK_URL,
    }

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE calls
            SET state = 'sending'
            WHERE request_id = ?
            AND state = 'prepared'
            """,
            (request_id,),
        )

    try:
        response = client.create_call(payload)

        # Support provider clients that return an httpx.Response
        # or a (status_code, response_data) tuple.
        if isinstance(response, httpx.Response):
            status_code = response.status_code
            try:
                response_data = response.json()
            except ValueError:
                response_data = {}

        elif isinstance(response, tuple) and len(response) == 2:
            status_code, response_data = response

        else:
            raise TypeError(
                "Unexpected TelephonyClient.create_call return type"
            )

        if status_code in (200, 201):
            call_sid = response_data.get("call_sid")

            if not call_sid:
                raise ValueError("Accepted call missing call_sid")

            record_accepted_call(request_id, call_sid)

        handle_call_response(
            request_id,
            status_code,
            response_data,
        )

        logger.info(
            "Call %s: HTTP %s",
            request_id,
            status_code,
        )

    except (httpx.RequestError, ValueError, TypeError) as exc:
        # Unknown outcome: never immediately create a new request ID.
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE calls
                SET state = 'uncertain'
                WHERE request_id = ?
                AND state != 'ended'
                """,
                (request_id,),
            )

        logger.warning(
            "Uncertain call %s: %s",
            request_id,
            exc,
        )


def recover_unfinished(client):
    for call in get_unfinished_calls():
        request_id = call["request_id"]

        try:
            result = reconcile_call(request_id, client)

            if result == "not_found":
            # Do not resend outside the campaign's calling window.
                from solution.scheduler import is_calling_allowed

                now = get_simulated_now(client)

                campaign = next(
                    c for c in load_config()["campaigns"]
                        if c["campaign_id"] == call["campaign_id"]
                    )

                if is_calling_allowed(campaign, now):
                    send_reserved_call(client, call)
                else:
                    logger.info(
                        "Deferring recovery of %s: outside calling window",
                        request_id,
                    )

            elif result == "recovered_active":
                record_accepted_call(
                    request_id,
                    call_sid=None,
                )

            elif result == "recovered_ended":
                logger.info("Recovered ended call %s", request_id)

            elif result not in ("already_resolved",):
                logger.warning(
                    "Recovery %s: %s",
                    request_id,
                    result,
                )

        except Exception:
            logger.exception("Recovery failed for %s", request_id)


def run():
    initialize_database()
    load_leads()

    config = load_config()
    logger.info(
        "Starting dispatcher for %s campaigns",
        len(config["campaigns"]),
    )

    client = TelephonyClient()

    try:
        while True:
            try:
                now = get_simulated_now(client)

                # Recover first to preserve concurrency and phone locks.
                recover_unfinished(client)

                candidates = get_candidates()

                for lead in candidates:
                    now = get_simulated_now(client)
                # Reuse the simulated time obtained at the start
                # of this scheduling cycle.

                    request_id, reason = reserve_call_safely(
                        lead["campaign_id"],
                        lead["lead_id"],
                        now,
                    )

                    if request_id is None:
                        continue

                    with get_connection() as connection:
                        call = connection.execute(
                            """
                            SELECT *
                            FROM calls
                            WHERE request_id = ?
                            """,
                            (request_id,),
                        ).fetchone()

                    send_reserved_call(client, dict(call))

                with get_connection() as connection:
                    remaining = connection.execute(
                        """
                        SELECT COUNT(*)
                        FROM leads
                        WHERE state = 'pending'
                        """
                    ).fetchone()[0]

                logger.info(
                    "Simulated time: %s | Pending leads: %s",
                    now.isoformat(),
                    remaining,
                )

                if remaining == 0 and not get_unfinished_calls():
                    logger.info("All leads finalized")
                    break

            except Exception:
                logger.exception("Dispatcher loop error")

            time.sleep(0.5)

    finally:
        client.close()


if __name__ == "__main__":
    run()
