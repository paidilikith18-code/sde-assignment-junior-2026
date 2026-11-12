from datetime import datetime, time
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

DAY_NAMES = [
    "mon", "tue", "wed", "thu", "fri", "sat", "sun"
]


def is_calling_allowed(campaign, simulated_now):
    """Check campaign and regulatory calling windows."""

    now = simulated_now.astimezone(IST)

    window = campaign["window"]

    allowed_days = [day.lower()[:3] for day in window["days"]]

    current_day = DAY_NAMES[now.weekday()]

    if current_day not in allowed_days:
        return False

    start = time.fromisoformat(window["start"])
    end = time.fromisoformat(window["end"])

    regulatory_start = time(9, 0)
    regulatory_end = time(21, 0)

    current_time = now.time().replace(tzinfo=None)

    return (
        start <= current_time < end
        and regulatory_start <= current_time < regulatory_end
    )


from datetime import timedelta


def next_eligible_time(status, disposition, ended_at, callback_at=None):
    """Calculate the earliest time a lead can be called again."""

    if disposition == "callback_requested":
        if callback_at is None:
            raise ValueError("callback_requested requires callback_at")
        return datetime.fromisoformat(callback_at)

    if ended_at is None:
        raise ValueError("ended_at is required for retry scheduling")

    ended = datetime.fromisoformat(ended_at)

    if status in ("no_answer", "busy"):
        return ended + timedelta(minutes=60)

    if status == "failed":
        return ended + timedelta(minutes=15)

    return None


def lead_priority(disposition, attempts):
    """Lower number means higher scheduling priority."""

    if disposition == "callback_requested":
        return 0

    if attempts > 0:
        return 1

    return 2


def next_calling_time(campaign, eligible_at):
    """
    Find the earliest permitted calling time at or after eligible_at.

    Uses campaign windows, allowed weekdays, and regulatory hours.
    """
    from datetime import timedelta

    if eligible_at.tzinfo is None:
        raise ValueError("eligible_at must have timezone information")

    candidate = eligible_at.astimezone(IST)

    window = campaign["window"]
    campaign_start = time.fromisoformat(window["start"])
    campaign_end = time.fromisoformat(window["end"])

    effective_start = max(campaign_start, time(9, 0))
    effective_end = min(campaign_end, time(21, 0))

    if effective_start >= effective_end:
        raise ValueError("Campaign has no valid calling hours")

    for day_offset in range(8):
        day = candidate.date() + timedelta(days=day_offset)

        opening = datetime.combine(day, effective_start, tzinfo=IST)

        if day_offset == 0:
            possible_time = max(candidate, opening)
        else:
            possible_time = opening

        if is_calling_allowed(campaign, possible_time):
            return possible_time

    raise ValueError("No valid calling window found within 8 days")
