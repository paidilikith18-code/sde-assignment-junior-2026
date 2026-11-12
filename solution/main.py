import json
import logging

from fastapi import FastAPI, HTTPException, Request

from solution.result_processor import process_call_result
from solution.webhook import verify_webhook_signature

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Durable Campaign Dispatcher")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/webhooks/telephony")
async def telephony_webhook(request: Request):
    raw_body = await request.body()
    signature = request.headers.get("X-AU-Signature")

    if not verify_webhook_signature(raw_body, signature):
        raise HTTPException(
            status_code=401,
            detail="Invalid webhook signature",
        )

    try:
        payload = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(
            status_code=400,
            detail="Invalid JSON payload",
        )

    if payload.get("event") != "call.completed":
        raise HTTPException(
            status_code=400,
            detail="Unsupported webhook event",
        )

    try:
        result = process_call_result(payload)
    except (KeyError, ValueError, TypeError) as exc:
        logger.warning("Webhook rejected: %s", exc)
        raise HTTPException(
            status_code=400,
            detail="Invalid or unknown call result",
        )

    return {"received": True, "result": result}
