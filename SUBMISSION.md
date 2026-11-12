# Submission

## Candidate
- **Name:** [Your full name]
- **Assignment chosen:** B (Workflow)
- **Time spent (honest estimate):** [Enter actual hours]

## How to run

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Start the mock telephony provider in terminal 1:

```bash
cd assignment-b-workflow
python -m mock_telephony --failure-scale 0
```

Start the webhook receiver from the repository root in terminal 2:

```bash
python -m uvicorn solution.main:app --host 127.0.0.1 --port 8200
```

Start the dispatcher from the repository root in terminal 3:

```bash
python -m solution.runner
```

After all leads are finalized, export the results:

```bash
python -m solution.export
```

Run tests:

```bash
python -m pytest -q
```

The final CSV is generated at `solution/final_state.csv`.

## Design

The solution uses Python, SQLite, FastAPI, and HTTPX.

The dispatcher loads campaigns and leads, checks campaign calling windows, regulatory restrictions, retry eligibility, DND restrictions, and tenant concurrency limits before placing calls.

SQLite stores lead states, call records, accepted-attempt counts, and globally blocked phone numbers.

A database transaction reserves each call with a unique request ID before contacting the provider. The same request ID is reused when recovering an uncertain request, allowing provider-side idempotency to prevent duplicate dialing.

The webhook receiver validates HMAC signatures before processing call results.

### Lead state machine

```text
                 +---------+
                 | Pending |
                 +----+----+
                      |
                 Eligible call
                      |
              Provider accepts
                      |
                 Call result
                      |
        +-------------+-------------+
        |             |             |
     Terminal       Retry        DND restriction
        |             |             |
        v             v             v
   Completed       Pending      DND Blocked
                      |
               Attempts exhausted
                      |
                      v
                  Exhausted
```

### Recovery strategy

Call reservations are persisted before external HTTP requests.

If a request times out or its result is uncertain, the dispatcher can query the provider using its original request ID.

Accepted attempts are counted idempotently using the persisted `attempt_counted` field.

Webhook processing and recovery update the same persistent call and lead records.

## Decisions & assumptions

| Decision | Why | Alternative considered |
|---|---|---|
| SQLite with WAL mode | Lightweight persistence and transactional reservations | External database |
| Stable UUID request IDs | Supports provider-side idempotency and crash recovery | Generating new IDs for retries |
| FastAPI webhook receiver | Simple HTTP endpoint with signature verification | Polling only |
| HTTPX provider client | Explicit control over requests and responses | Larger workflow framework |
| Persistent accepted-attempt tracking | Prevents counting duplicate webhook or recovery events twice | In-memory counters |
| Simulated clock synchronization | Reduces repeated provider clock requests | Fetching the clock for every lead |

## Failure modes considered

- Duplicate lead loading: protected by database uniqueness and insert-ignore behavior.
- Duplicate call acceptance: stable request IDs and provider reconciliation.
- Duplicate result processing: persisted call state and idempotent attempt counting.
- HTTP timeouts and uncertain responses: reconciled using provider lookups.
- Missing webhook results: recovered by querying unfinished provider calls.
- Process restart: persistent SQLite records allow recovery.
- Calling-window and concurrency violations: checked before reservations.
- Global DND restrictions: stored in a shared phone-level table.

Limitations:
- The current implementation uses local SQLite and a single-machine deployment.
- A complete automated crash-injection test suite has not yet been added.
- Further testing under nonzero provider failure injection is needed before claiming full resilience.

## Testing

Automated tests currently verify:
- The exported CSV contains 200 leads.
- Lead keys are unique.
- Records are sorted.
- Every lead has a terminal state.
- Accepted attempts remain within the configured limit.

Full integration testing verified:
- 200 lead records matched the provider's expected results.
- All final states, attempts, statuses, and dispositions matched.
- No provider rule violations were reported.
- All 407 webhooks were delivered.

## Results

Final provider report:

```text
Total calls:             407
Completed calls:         222
Failed calls:             25
Busy calls:               52
No-answer calls:         108
Active calls:              0
Provider violations:       0
Webhooks delivered:      407

Maximum concurrency:
  acme_insurance:          4
  zen_retail:              3

Callback lateness:
  p50:                    3.3 minutes
  p90:                    4.9 minutes
  max:                    5.3 minutes

Final lead comparison:
  Expected records:       200
  Exported records:       200
  Mismatches:               0
```

This run used `--failure-scale 0`. It therefore does not establish behavior under injected provider failures.

## If I had another day

1. Add automated crash-restart and ambiguous-response tests.
2. Test with provider failure injection enabled.
3. Add concurrency and scheduling boundary tests using a controllable simulated clock.
4. Improve structured logging and operational monitoring.
5. Evaluate a production database and multi-worker deployment strategy.