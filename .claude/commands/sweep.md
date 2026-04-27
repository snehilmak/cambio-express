---
description: Run a one-PR cleanup sweep on the codebase (dedup + simplify + tests). Designed for unattended runs from claude.ai/code/routines.
allowed-tools: Read, Grep, Glob, Edit, Write, Bash, Agent
---

# /sweep — agent-team cleanup pass

Execute a single, narrow cleanup sweep on `cambio-express`. Designed
to run unattended from a Routines schedule and produce ONE
reviewable PR.

## Pre-flight

1. Confirm working tree is clean. If not, abort:
   > "Working tree is dirty; refusing to sweep."
2. Run `pytest tests/ -x -q`. If anything fails before sweep starts,
   abort:
   > "Baseline tests are red; refusing to sweep."
3. Read `/home/user/cambio-express/.claude/AGENTS.md` and
   `/home/user/cambio-express/CLAUDE.md` in full.
4. Create a fresh branch: `git checkout -b claude/sweep-$(date +%Y%m%d-%H%M)`.

## Sweep

Run these subagents **in parallel** (single message, multiple
Agent tool calls):

- `dedup-hunter` — find one extraction worth applying.
- `simplifier` — find dead branches and pointless wrappers.

Wait for both. Then run sequentially:

- `test-writer` — add tests for one untested target.

## Gate before commit

After all three agents have run:
1. `pytest tests/ -x -q` — must pass.
2. `python3 -m py_compile app.py` — must succeed.
3. `git diff --stat` — diff budget is < 600 lines net total across
   all three agents combined. If over budget, revert the largest
   single agent's changes (typically test-writer) and re-gate.

If any gate fails, run `git checkout .` and report:
> "Sweep produced changes that failed the gate. Branch discarded.
> See logs for details."

## Commit and PR

If gate passes:

1. Stage the changes you want (review per-file with `git diff` and
   stage explicitly — never `git add -A`).
2. Commit message format:
   ```
   sweep: <one-line summary of all three agents' work>

   - dedup: <dedup-hunter summary or "skipped">
   - simplify: <simplifier summary or "skipped">
   - tests: <test-writer summary or "skipped">

   Diff: <-N / +M> lines net
   Suite: <290 → 295 tests, all passing>
   ```
3. Push the branch.
4. Open a PR against `main` titled
   `sweep: <topic> (<date>)`. Body must include each agent's
   report verbatim plus the gate output.
5. Subscribe to PR activity (you'll handle CI failures and review
   comments per CLAUDE.md's PR monitoring section).

## What this command will NOT do

- Will not edit templates, CSS, or anything visual.
- Will not edit `requirements.txt`.
- Will not edit `_ADDED_COLUMNS`, `_STORE_OWNED_MODELS`, or any DB
  schema.
- Will not delete public routes, models, or templates.
- Will not skip or delete tests to make a sweep pass.
- Will not push to `main` directly.

If you find something that needs one of the above, write it into
the PR body under "Deferred — needs human review" instead of
applying it.
