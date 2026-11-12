import uuid

from solution.database import get_connection


def reserve_call(campaign_id, lead_id):
    """
    Persist a stable request_id before contacting the provider.

    Reuse an existing unfinished reservation on repeated calls.
    """
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")

        lead = connection.execute(
            """
            SELECT campaign_id, lead_id, phone, state
            FROM leads
            WHERE campaign_id = ? AND lead_id = ?
            """,
            (campaign_id, lead_id),
        ).fetchone()

        if lead is None:
            raise ValueError("Lead not found")

        if lead["state"] != "pending":
            raise ValueError("Lead is not pending")

        existing = connection.execute(
            """
            SELECT request_id
            FROM calls
            WHERE campaign_id = ?
            AND lead_id = ?
            AND state IN ('prepared', 'sending', 'active', 'uncertain')
            ORDER BY rowid DESC
            LIMIT 1
            """,
            (campaign_id, lead_id),
        ).fetchone()

        if existing:
            return existing["request_id"]

        request_id = str(uuid.uuid4())

        connection.execute(
            """
            INSERT INTO calls (
                request_id,
                campaign_id,
                lead_id,
                phone,
                state
            )
            VALUES (?, ?, ?, ?, 'prepared')
            """,
            (
                request_id,
                campaign_id,
                lead_id,
                lead["phone"],
            ),
        )

        return request_id


from solution.config import load_config
from solution.scheduler import is_calling_allowed
from datetime import datetime


def can_dispatch(campaign_id, lead_id, simulated_now):
    """
    Check whether a lead can be dispatched safely.

    Returns (allowed, reason).
    """
    config = load_config()

    campaign = next(
        (
            c for c in config["campaigns"]
            if c["campaign_id"] == campaign_id
        ),
        None,
    )

    if campaign is None:
        return False, "campaign_not_found"

    if not is_calling_allowed(campaign, simulated_now):
        return False, "outside_calling_window"

    with get_connection() as connection:
        lead = connection.execute(
            """
            SELECT *
            FROM leads
            WHERE campaign_id = ? AND lead_id = ?
            """,
            (campaign_id, lead_id),
        ).fetchone()

        if lead is None:
            return False, "lead_not_found"

        if lead["state"] != "pending":
            return False, "lead_not_pending"

        if lead["attempts"] >= campaign["max_attempts"]:
            return False, "max_attempts_reached"

        blocked = connection.execute(
            "SELECT 1 FROM dnd_phones WHERE phone = ?",
            (lead["phone"],),
        ).fetchone()

        if blocked:
            return False, "dnd_blocked"

        if lead["next_eligible_at"]:
            eligible_at = datetime.fromisoformat(
                lead["next_eligible_at"]
            )

            if simulated_now < eligible_at:
                return False, "retry_or_callback_not_due"

        active_phone = connection.execute(
            """
            SELECT 1
            FROM calls
            WHERE phone = ?
            AND state IN ('prepared', 'sending', 'active', 'uncertain')
            LIMIT 1
            """,
            (lead["phone"],),
        ).fetchone()

        if active_phone:
            return False, "phone_already_reserved"

        tenant = next(
            t for t in config["tenants"]
            if t["tenant_id"] == lead["tenant_id"]
        )

        active_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM calls c
            JOIN leads l
            ON c.campaign_id = l.campaign_id
            AND c.lead_id = l.lead_id
            WHERE l.tenant_id = ?
            AND c.state IN ('prepared', 'sending', 'active', 'uncertain')
            """,
            (lead["tenant_id"],),
        ).fetchone()[0]

        if active_count >= tenant["max_concurrent_calls"]:
            return False, "tenant_concurrency_limit"

    return True, "eligible"


def reserve_call_safely(campaign_id, lead_id, simulated_now):
    """
    Atomically check eligibility and reserve a call.

    Returns (request_id, reason).
    """
    config = load_config()

    campaign = next(
        (c for c in config["campaigns"]
        if c["campaign_id"] == campaign_id),
        None,
    )

    if campaign is None:
        return None, "campaign_not_found"

    if not is_calling_allowed(campaign, simulated_now):
        return None, "outside_calling_window"

    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")

        lead = connection.execute(
            """
            SELECT *
            FROM leads
            WHERE campaign_id = ? AND lead_id = ?
            """,
            (campaign_id, lead_id),
        ).fetchone()

        if lead is None:
            return None, "lead_not_found"

        if lead["state"] != "pending":
            return None, "lead_not_pending"

        if lead["attempts"] >= campaign["max_attempts"]:
            return None, "max_attempts_reached"

        if lead["next_eligible_at"]:
            eligible_at = datetime.fromisoformat(
                lead["next_eligible_at"]
            )
            if simulated_now < eligible_at:
                return None, "retry_or_callback_not_due"

        blocked = connection.execute(
            "SELECT 1 FROM dnd_phones WHERE phone = ?",
            (lead["phone"],),
        ).fetchone()

        if blocked:
            return None, "dnd_blocked"

        phone_busy = connection.execute(
            """
            SELECT 1
            FROM calls
            WHERE phone = ?
            AND state IN ('prepared', 'sending', 'active', 'uncertain')
            LIMIT 1
            """,
            (lead["phone"],),
        ).fetchone()

        if phone_busy:
            return None, "phone_already_reserved"

        tenant = next(
            t for t in config["tenants"]
            if t["tenant_id"] == lead["tenant_id"]
        )

        active_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM calls c
            JOIN leads l
            ON c.campaign_id = l.campaign_id
            AND c.lead_id = l.lead_id
            WHERE l.tenant_id = ?
            AND c.state IN ('prepared', 'sending', 'active', 'uncertain')
            """,
            (lead["tenant_id"],),
        ).fetchone()[0]

        if active_count >= tenant["max_concurrent_calls"]:
            return None, "tenant_concurrency_limit"

        request_id = str(uuid.uuid4())

        connection.execute(
            """
            INSERT INTO calls (
                request_id,
                campaign_id,
                lead_id,
                phone,
                state
            )
            VALUES (?, ?, ?, ?, 'prepared')
            """,
            (
                request_id,
                campaign_id,
                lead_id,
                lead["phone"],
            ),
        )

        return request_id, "reserved"
