---
description: Add pytest tests for one untested target (route or helper).
allowed-tools: Read, Grep, Glob, Edit, Write, Bash, Agent
---

# /add-tests

Run the `test-writer` subagent on `cambio-express`.

Steps:
1. Working tree clean.
2. Baseline `pytest tests/ -x -q` — note the count.
3. Spawn `test-writer`.
4. Re-run `pytest tests/ -x -q` — count must be higher and all
   must pass.
5. Stage, commit `tests: cover <target>`, show diff stat. Don't push.
