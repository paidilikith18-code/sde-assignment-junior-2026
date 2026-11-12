# AI Usage Disclosure

## Tools used

ChatGPT (OpenAI).

## What I used them for

I used ChatGPT as a Python backend engineering assistant throughout Assignment B.

It helped me:
- Understand the assignment requirements and plan the implementation.
- Develop and refine the SQLite schema, dispatcher, scheduler, provider client, and recovery logic.
- Implement the FastAPI webhook receiver and HMAC signature verification.
- Debug integration issues using terminal logs, provider reports, and SQLite queries.
- Develop the final CSV exporter and initial pytest validation tests.
- Draft implementation and submission documentation.

## What I wrote or decided myself

I selected Assignment B, executed the implementation locally, ran the integration tests, inspected the output, and worked through the debugging steps.

I reviewed the terminal results and used the provider's report and expected lead data to verify the final behavior.


## Where the AI was wrong or unhelpful

An earlier integration run encountered webhook delivery failures because the FastAPI webhook receiver was not running.

The provider reported webhook connection errors, revealing that the full service startup sequence had not been verified.

I addressed this by starting the webhook receiver and verifying its health endpoint before repeating the integration run.

The successful run subsequently delivered all 407 webhooks.

## How I verified AI-generated code

I used:
- Python compilation checks.
- Local HTTP health checks.
- SQLite queries to inspect lead and call states.
- Mock-provider reports to inspect violations and concurrency.
- Automated pytest validation tests.
- A full integration run with 200 leads.
- A field-by-field comparison of the exported CSV against the provider's 200 expected records.

The final comparison reported zero mismatches, and the provider reported zero rule violations.