import httpx

PROVIDER_URL = "http://127.0.0.1:8099"


class TelephonyClient:
    def __init__(self):
        self.client = httpx.Client(
            base_url=PROVIDER_URL,
            timeout=10.0,
        )

    def get_clock(self):
        response = self.client.get("/v1/clock")
        response.raise_for_status()
        return response.json()

    def create_call(self, payload):
        """
        Send a call request using a previously persisted request_id.

        Do not automatically generate a new request_id here.
        """
        return self.client.post("/v1/calls", json=payload)

    def find_call(self, request_id):
        """
        Look up a call using its idempotency key.
        Useful after crashes or ambiguous 504 responses.
        """
        response = self.client.get(
            "/v1/calls",
            params={"request_id": request_id},
        )
        response.raise_for_status()
        return response.json()

    def get_call(self, call_sid):
        response = self.client.get(f"/v1/calls/{call_sid}")
        response.raise_for_status()
        return response.json()

    def close(self):
        self.client.close()
