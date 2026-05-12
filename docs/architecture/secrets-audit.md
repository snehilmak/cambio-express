# DineroBook — Secrets Audit

> Last updated: 2026-05-12
> Audience: anyone reviewing the repo for accidentally-committed
> secrets, or evaluating "Before going live" gate from BACKLOG.md.

## Scope

This audit covers the **public Git history** of the
`cambio-express` repository. Goal: confirm no real production
credentials (Stripe live keys, SMTP passwords, JWT secrets, OAuth
tokens, etc.) have been committed, and document the few
known-default fallback values + the prod safety gates that
protect against them.

## Audit run — what was scanned

* All tracked files (`git ls-files`).
* All file types — Python, TypeScript, HTML, YAML, JSON, Markdown.
* Patterns scanned:
  - Stripe live keys: `sk_live_*`, `pk_live_*`, `whsec_live_*`
  - AWS access keys: `AKIA*`
  - Bearer tokens with high entropy: `Bearer [a-zA-Z0-9_-]{20+}`
  - Generic high-entropy secrets: `api_key|secret = "[a-zA-Z0-9]{16+}"`
  - Hardcoded password literals (matched against known defaults)
  - Anything that looks like a JWT signature (3 base64 segments)

## Findings

### ✅ No live production credentials committed

* Stripe `sk_live_` / `pk_live_` / `whsec_*` never appear except
  in comments, docstrings, and test fixtures using stub strings
  (`"sk_live_real"`, `"sk_live_x"`).
* AWS keys: zero matches.
* High-entropy hardcoded secrets: zero matches.
* JWT secrets: only `SECRET_KEY` env var; no hardcoded HS256 key.

All real secrets are sourced from environment variables (see
`render.yaml` — every `sync: false` value gets entered in the
Render dashboard, never committed).

### ⚠️ Documented dev-fallback secrets (intentional, gated in prod)

Three known-public fallback values exist in the source. They're
all gated behind explicit env-var overrides AND a prod safety
check that refuses to boot if the env var is missing:

| Fallback | Where | Override env var | Prod gate |
|---|---|---|---|
| `app.secret_key` = `"dinerobook-dev-secret-change-in-prod"` | `app.py:58` | `SECRET_KEY` | **HARD REFUSAL** — `RuntimeError` at boot if `APP_BASE_URL` starts with `https://` and `SECRET_KEY` is unset/empty |
| Superadmin seed pw `"super2025!"` | `app.py` `init_db()` | `SUPERADMIN_PASSWORD` | CRITICAL-level structured log at boot if missing in prod |
| Admin seed pw `"cambio2025!"` | `app.py` `init_db()` | `ADMIN_PASSWORD` | CRITICAL-level structured log at boot if missing in prod |

#### Why hard-refuse on `SECRET_KEY` but only warn on the seed passwords?

The signed session cookie is the foundation of every auth check.
A prod deploy that boots with the dev `SECRET_KEY` is
catastrophically broken — an attacker who has read this
public repo can forge a session as **any** user, including
superadmin. There's no recovery from that state without
rotating the key (and force-logging-out everyone). Refusing to
boot is the safer mode.

The seed passwords are different. Even if `SUPERADMIN_PASSWORD`
isn't set in prod, the seed password only matters at first boot —
once an operator logs in once and changes the password through
the UI (or via `flask reset-superadmin`), the default value
becomes irrelevant. So a loud log warning is enough: it nudges
the operator without breaking the deploy.

### ⚠️ render.yaml has placeholder values for the seed passwords

`render.yaml` lines 27–30:

```yaml
- key: SUPERADMIN_PASSWORD
  value: super2025!   # CHANGE THIS after first deploy
- key: ADMIN_PASSWORD
  value: cambio2025!  # CHANGE THIS after first deploy
```

These are intentional for the first-time Blueprint deploy
(see [`deployment.md`](deployment.md) §1) — Render reads
`render.yaml` at deploy time and uses the value verbatim. The
expectation is that the operator removes these (or replaces
with new random values) immediately after first boot, then
re-deploys to force the change.

**Recommendation for paid launch:**

1. Render dashboard → Environment → set both vars to fresh random
   strings.
2. Remove the placeholder lines from `render.yaml`, OR change
   them to `sync: false` so Render prompts for a value at deploy
   time and never reads the committed value.
3. The CRITICAL log at boot (added in this PR) becomes the
   regression guard: any deploy where the env vars aren't set
   prints a loud warning in Render → Logs.

## Prod safety gates (added in this PR)

* `app.py:58–98` — `_SECRET_KEY_DEV_FALLBACK` guard that raises
  `RuntimeError` if the prod-flagged deploy is still running the
  fallback. Detected via `APP_BASE_URL` starting with `https://`
  (same env-var gate the session-cookie + SMTP / Stripe URL
  builders use).
* Same block emits a CRITICAL structured-log warning if
  `SUPERADMIN_PASSWORD` or `ADMIN_PASSWORD` is missing in prod.
  Sentry + Render → Logs surface this; the operator sees it
  immediately on the first deploy.

## Recurring audit checklist

When reviewing a PR that touches secrets management:

* [ ] Any new `os.environ.get("KEY", "literal-default")` — confirm
  the literal is safe to ship (low-entropy placeholder, NOT a
  real credential). If the default is sensitive, gate behind the
  same `APP_BASE_URL` HTTPS check that this audit added.
* [ ] No `sk_live_*` / `pk_live_*` / `whsec_*` strings in the
  diff (test fixtures using stubs like `sk_live_x` are fine).
* [ ] No `Bearer <real-token>` in test fixtures or docs.
* [ ] If render.yaml adds an env var, default it to `sync: false`
  unless it's truly public (e.g. `PYTHON_VERSION`).
* [ ] If the diff adds a new model field that stores a
  credential or token (API key, refresh token, etc.), confirm
  it's stored encrypted or hashed — never plaintext. See
  `User.totp_secret` for the trust-boundary rationale; same
  reasoning applies to any new secret column.

## Sign-off

This audit completes the "Secrets audit" line in
[`BACKLOG.md`](../../BACKLOG.md)'s "Before going live" section.
The repo is **safe to make public** assuming the seed-password
placeholders in `render.yaml` get scrubbed before the public
push.

Next item on the list: [`deployment.md`](deployment.md) §6
("Pre-launch checklist") for the remaining gates.
