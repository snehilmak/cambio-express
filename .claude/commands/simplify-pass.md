---
description: Run a simplifier sweep — remove dead branches, pointless wrappers, redundant defensive code.
allowed-tools: Read, Grep, Glob, Edit, Bash, Agent
---

# /simplify-pass

Run the `simplifier` subagent on `cambio-express`.

Steps:
1. Working tree must be clean.
2. Baseline `pytest tests/ -x -q`.
3. Spawn `simplifier`.
4. Re-run `pytest tests/ -x -q`.
5. If green: stage, commit `simplify: <one-line summary>`, show diff
   stat. Don't push.
6. If red: revert and report which test broke.
