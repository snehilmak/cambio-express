# Agent Team — Shared Rules

This file is read by every subagent in `.claude/agents/` and every slash
command in `.claude/commands/`. It captures the **non-negotiable
invariants** from `/CLAUDE.md` in a form optimized for agents doing
unattended sweeps. If something in `CLAUDE.md` contradicts this file,
`CLAUDE.md` wins — update this file, don't drift.

## Hard rules — never violate

1. **DB API.** Use `db.session.get(Model, id)`. Never `Model.query.get(id)`.
2. **No column drops.** Never delete a column or table from a running
   DB. Adding a column means appending to `_ADDED_COLUMNS` at the bottom
   of `app.py` (idempotent on every boot).
3. **Per-store models go in `_STORE_OWNED_MODELS`.** If you add a new
   `db.Model` that has a `store_id` foreign key, it MUST be added to
   `_STORE_OWNED_MODELS` so retention purge cascades correctly.
4. **Superadmin mutations call `record_audit()`.** Any route under
   `/superadmin/*` that mutates state must record an audit entry.
5. **Stripe checkout keeps `allow_promotion_codes=True`.** Discount
   redemption depends on it.
6. **2FA finalization.** Password-flow login must NEVER set
   `session["user_id"]` directly for a role that `_needs_totp()` returns
   True for. Use `_finalize_2fa_login(user)` after a TOTP/recovery code
   succeeds. Passkey flow is the only carve-out (see CLAUDE.md §13).
7. **Trial-exempt routes.** New routes that must remain reachable when
   `Store.plan == "inactive"` go in `_TRIAL_EXEMPT`.
8. **Money math.** `Transfer.total_collected = send_amount + fee +
   federal_tax`. `ACHBatch.transfers_total = Σ(send_amount +
   federal_tax)`. Fee is store revenue, federal_tax leaves with the ACH.
9. **Customer upsert.** Only `find_or_upsert_customer()` creates or
   mutates `Customer` rows from the transfer form. Don't bypass it.
10. **Password reset tokens.** Store `sha256(raw)` in
    `PasswordResetToken.token_hash`. Never log the raw token on the
    success path.

## Design system — visual changes

- **Dark only.** No light mode. `data-theme="dark"` is unconditional.
- **One saturated color.** Neon green `#3fff00` is the only brand
  accent. Don't introduce another. Jewel tones (`--db-co-*`) and state
  tokens (`--db-info/warning/negative`) are the second layer.
- **Tokens, not hex.** Use `--db-*` from `static/design-tokens.css`.
  If you need a new color, add a token there with a comment.
- **Semantic tokens for surfaces.** `--surface`, `--surface-2`,
  `--surface-sticky`, `--text`, `--text-muted`, `--border`,
  `--border-strong`. These flip in dark mode. Fixed brand tokens
  (`--navy`, `--gold`, `--white`, `--gray*`, `--cream`) do NOT flip —
  only use them for color that should stay constant.
- **Three fonts only.** Space Grotesk (display), Inter (body),
  JetBrains Mono (money/dates/IDs). No others.
- **Reuse before rolling.** Check `docs/design-system/project/ui_kits/`
  and `static/content.css` for existing classes (`.card`, `.stat-card`,
  `.section-box`, `.quick-link-card`, `.sb-*`, `.mt-table`,
  `.sticky-save-bar`) before writing new CSS.
- **Live-search standard.** Every paginated table uses the debounced
  AJAX pattern: 300ms debounce, 2-char min, AbortController,
  `history.replaceState`, `?partial=1` route branch returning JSON.
  Reference: `templates/transfers.html` + `templates/_transfers_table.html`.

## Style — when editing code

- Don't add features, refactors, or abstractions beyond what the task
  requires. Three similar lines is better than a premature abstraction.
- Default to no comments. Only add one when the WHY is non-obvious
  (hidden constraint, subtle invariant, workaround for a specific bug).
- Don't explain WHAT the code does — names should do that.
- No backwards-compat shims for deletes (`# removed` markers, unused
  re-exports, renamed `_var` placeholders). Delete it cleanly.
- No new error handling for impossible states. Validate at system
  boundaries (user input, external APIs), trust internal callers.

## Test floor

- `pytest tests/` must stay green on every commit.
- New routes must have a test. Use fixtures in `tests/conftest.py`
  (in-memory SQLite, seeded superadmin, one trial store).
- Never delete or skip tests to make a sweep pass — fix the code or
  flag the test as a real regression and stop.

## Sweep etiquette (autonomous runs)

These rules apply specifically to unattended `/sweep` runs from the
Routines scheduler:

- **One PR per sweep run.** Don't fan out multiple PRs from one run.
- **Scope is narrow.** A sweep should touch one concern (dedup, OR
  simplify, OR tests) — not a grand restructure.
- **Stop on red.** If `pytest -x` fails after edits, revert the edits
  and report the failure. Don't push broken code.
- **No design drift.** Don't introduce new tokens, fonts, components,
  or color values during a sweep. UI work needs a human in the loop.
- **No schema changes.** Don't add columns or tables in a sweep.
  Schema work needs a human in the loop.
- **No new dependencies.** Don't add to `requirements.txt` in a sweep.
- **No deletions of public routes / templates / models.** Renames,
  moves, and outright removals need a human review — flag in the PR
  body, don't execute.
- **Diff budget.** Aim for a sweep PR diff of < 400 lines net. If the
  cleanup you found is bigger, summarize it in the PR description as
  "deferred — too large for unattended sweep" and don't apply it.
