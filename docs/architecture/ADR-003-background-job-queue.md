# ADR-003 — Background job queue (RQ + Redis)

> **Status:** PROPOSED.
> **Last updated:** 2026-05-11
> **Authors:** Claude (drafting).
> **Tracked by:** BACKLOG.md item D5.

## Context

Every long-running side effect in the product today runs **inside the
HTTP request**:

- **Stripe webhooks** (`/webhooks/stripe`) — on
  `checkout.session.completed` we read the customer, look up the
  store, update the plan, mint or apply a referral code, optionally
  call `create_balance_transaction`, write an audit row, and send a
  confirmation email. All synchronous. A slow Stripe API leg blocks
  the webhook return; Stripe retries on >5s timeouts and our handler
  must be idempotent (it is, but the retries still cost work).
- **Password reset / invite emails** — sent inline via Resend during
  the request. A slow Resend hop adds latency to user-facing
  responses.
- **ACH retries / bank-sync refreshes** — kicked off by user clicks;
  Stripe Financial Connections refreshes can take 5–15s. The user
  watches a spinner.
- **Data-retention purge** — runs as a Flask CLI command
  (`flask purge-expired-stores`) on a Render cron schedule. Works
  fine for now but is a one-shot synchronous script with no
  visibility into per-store progress and no retry on a partial
  failure.
- **Daily-book end-of-day rollups and monthly-P&L freezes** — the
  user clicks "save" and the request rolls up the entire month.
  Today this is fast enough (<1s for a normal store) but it scales
  with row count.

Costs of doing everything inline:

- **User-visible latency.** Confirmation emails, Stripe writes,
  and FC refreshes all block the user.
- **Webhook reliability is fragile.** A Stripe webhook is supposed
  to be ack'd in <5s. We're inside the limit today, but a slower
  email send or a transient Stripe API hiccup pushes us over.
- **No retry semantics.** When an email send fails today, we log it
  and move on. The user thinks they got the email; they didn't.
- **No backpressure.** If 200 webhooks land at once (unlikely but
  possible during a Stripe outage recovery), the web workers do
  all the work serially.

## Decision

**Adopt RQ (Redis Queue) on Render's managed Redis** as the
background-job runtime. Every side effect that doesn't need to be
done before returning the HTTP response moves to an RQ job.

Concretely:

- **One Redis instance.** Render-managed, smallest tier to start.
  Same network as the web service, no public exposure.
- **One RQ worker process** initially, deployed as a separate Render
  service (`dinerobook-worker`) running off the same image as the
  web service. Two queues: `default` and `webhooks`. The `webhooks`
  queue gets a higher priority worker to keep Stripe ack latency
  low.
- **Job definitions** live in `api/Core/Jobs/` — one module per
  side-effect family (`stripe_webhook_handlers`, `email`,
  `retention`, `bank_sync`).
- **Enqueue from anywhere** via a thin `enqueue(job_name, *args)`
  helper that lives in `api/Core/Jobs/__init__.py`. Web request
  handlers call `enqueue`; the job does the actual work.
- **Idempotency keys** on every job. Re-enqueuing the same job
  (Stripe webhook redelivery, retry-on-failure) hits a Redis SET
  guard before doing the work.
- **Dead-letter queue** for jobs that exhaust their retries; a
  superadmin UI panel surfaces it so we can inspect failures.

## Consequences

What this unlocks:

- **Sub-100ms webhook ack.** Stripe webhook handler reads the event,
  enqueues a job, returns 200. The job does the actual work async.
- **Retry-with-backoff for free.** RQ has built-in retry (`@job(...,
  retry=Retry(max=3, interval=[10, 60, 300]))`). Failed jobs land
  in the DLQ instead of vanishing.
- **Visibility.** RQ comes with a `rq info` CLI and a small
  dashboard (`rq-dashboard`); we wire it into superadmin so we can
  see queue depth, failure rate, and per-job runtime.
- **Cron consolidation.** The retention purge and any future
  scheduled jobs (e.g. nightly digest emails — BACKLOG `Email locked-
  day digest`) move to RQ's scheduler (`rq-scheduler`) instead of
  Render cron. One place to look for "what runs on a schedule."

What gets harder:

- **One more process to deploy and monitor.** The worker service
  needs its own health check + restart policy. Mitigation: start
  with one worker; horizontal-scale only if queue depth grows.
- **Job code can't read Flask's `request`-bound context.** A job
  runs outside any HTTP request, so anything that today implicitly
  grabs `current_user` from a Flask session has to be passed
  explicitly (user_id, store_id) as a job arg. Already true for the
  existing CLI commands; we just have more of them now.
- **Two failure modes for emails.** "Job enqueued successfully but
  the worker hasn't picked it up yet" looks like "email never
  sent" from the user's perspective. Mitigation: surface enqueue
  errors directly to the user (don't silently swallow);
  enqueue-success means "guaranteed delivery within the SLA we
  pick."

What we accept:

- **A Redis dependency** for production deploys. Customer-deployable
  Docker images (per MIGRATION_ADR.md §3) will need a Redis
  sidecar. Acceptable cost — Redis runs as one container.
- **Eventually-consistent side effects.** A user who clicks
  "subscribe" and refreshes immediately may not see the plan change
  reflected for a few hundred ms. We mitigate by writing the
  plan change synchronously inside the webhook (it's a fast DB
  update) and only enqueuing the *follow-on* work (email, audit,
  referral credit application).

## Alternatives

| Option | Why we didn't pick it |
|---|---|
| Celery + RabbitMQ | More mature than RQ, but heavier-weight and harder to operate on Render. Celery's killer feature (rich routing / chord / chain primitives) is overkill for our needs. |
| Celery + Redis | Same Redis backend, same Render-friendly story. Celery's API surface is bigger than we need and its task discovery is fiddly. RQ is "the simplest thing that works"; we can graduate to Celery if we hit RQ's ceiling. |
| Dramatiq | Solid, but smaller ecosystem than RQ and we don't get anything RQ doesn't already give us. |
| `asyncio.create_task` from inside FastAPI handlers | "Free" — no extra infra. But: (a) the task dies if the worker process restarts mid-job, (b) no retry, (c) no visibility, (d) breaks under any kind of multi-worker setup because the task lives on one specific worker. Acceptable only for fire-and-forget logging. |
| Render Cron only | What we have today for the retention purge. Works for one-shot scheduled jobs but doesn't help with event-triggered work (webhooks, email sends). |
| Cloud-provider queues (SQS, Pub/Sub) | Tightly couples us to a cloud vendor. We're on Render today; might run on Fly / Railway / customer infra tomorrow. RQ + Redis runs anywhere. |

## Implementation

Suggested PR sequence. Each step ships independently.

1. **Add Redis** to `render.yaml` as a managed dependency. Wire
   `REDIS_URL` env var into the web service.
2. **Add the RQ scaffolding** — `api/Core/Jobs/__init__.py` with the
   `enqueue` helper and a `make_worker()` factory. Add a
   `worker.py` entrypoint that boots an RQ worker on the
   `default` + `webhooks` queues.
3. **Add a second Render service** (`dinerobook-worker`) running
   `python worker.py`. Same image, same env, no public port.
4. **Move email sends.** `send_password_reset_email`,
   `send_invite_email`, etc. become enqueue calls. Existing
   callers don't change.
5. **Move Stripe webhook side-effects.** The webhook handler does:
   - Verify signature (synchronous, must happen in-request)
   - Parse event (synchronous)
   - Write the plan change row (synchronous — cheap and the user
     might refresh immediately)
   - Enqueue `apply_referral_credits`, `send_subscription_confirm_email`,
     `audit_subscription_change` (async)
   - Return 200
6. **Move bank-sync refresh** off the click path. The user click
   enqueues a refresh job; the SPA polls `/api/v2/bank/sync-status`
   until the job completes (or shows a spinner with cancel).
7. **Move retention purge** from Flask CLI to an RQ scheduled job.
   Render cron entry stays but it now just enqueues, doesn't do
   the work directly.
8. **Add rq-dashboard** behind superadmin auth so we can see queue
   state in production. (Or roll our own minimal status view —
   queue depth + DLQ count + failure rate.)

## Open questions

- **Idempotency-key strategy.** Stripe event ID is the natural key
  for webhook jobs. Email sends need a synthetic key (`reset:user_id:
  reset_token_id`). Workable but needs to be explicit on every job
  definition.
- **Worker concurrency.** RQ supports `--burst` (run one round and
  exit, useful for Render cron) and `--with-scheduler` (one worker
  also runs the scheduler). For an early-stage product one worker
  process with 2–4 concurrent jobs is plenty.
- **Backpressure on enqueue.** If Redis is down, what does
  `enqueue()` do? Default: raise to the caller, which means the
  HTTP request fails. Probably the right default — we'd rather see
  the failure than silently lose work — but worth confirming in the
  PR that lands step 2.

## Changelog

- **2026-05-11** — Initial draft, status PROPOSED.
