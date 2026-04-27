---
description: Find and extract one duplicated pattern. Read-then-edit single agent run.
allowed-tools: Read, Grep, Glob, Edit, Bash, Agent
---

# /dedupe

Run the `dedup-hunter` subagent on `cambio-express`. One extraction
per invocation.

Steps:
1. Confirm working tree is clean; otherwise abort.
2. Run `pytest tests/ -x -q` baseline.
3. Spawn the `dedup-hunter` agent.
4. After it reports, run `pytest tests/ -x -q` again. If anything
   broke, revert (`git checkout .`) and report.
5. If clean: stage, commit with message `dedup: <pattern>`, and
   show the diff stat to the user.

Do not push — leave the commit on the current branch for the user
to review and push (or PR) themselves.
