import hashlib
import hmac

from solution.config import load_config


def verify_webhook_signature(raw_body, received_signature):
    """
    Verify the provider's HMAC-SHA256 signature.

    The signature must be calculated over the exact raw request body.
    """
    if not received_signature:
        return False

    config = load_config()
    secret = config["webhook_secret"].encode("utf-8")

    expected_signature = hmac.new(
        secret,
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(
        expected_signature,
        received_signature,
    )
