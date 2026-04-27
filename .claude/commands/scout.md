---
description: Read-only refactor opportunity report. Lists what could be cleaned up, ranked by value/risk.
allowed-tools: Read, Grep, Glob, Bash, Agent
---

# /scout

Run the read-only `refactor-scout` subagent. Produces a prioritized
list of cleanup opportunities. No edits.

Use before scheduling a routine sweep, or any time you want to
understand what cleanup work is sitting in the codebase.
