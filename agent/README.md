# DineroBook site agent (Gilbarco)

A tiny watcher that runs on the store's back-office PC, watches
the folder where Gilbarco Passport writes its NAXML journal files,
and pushes each new file to DineroBook the moment it appears. The
server parses everything — the agent never needs an update when
parsing improves.

## Install (Windows back-office PC)

1. Install Python 3.9+ from python.org (check "Add to PATH").
   No pip packages are needed — the agent is standard library only.
2. Copy this folder (`dinerobook_agent.py` + `agent.ini.example`)
   to e.g. `C:\DineroBook\agent\`.
3. In DineroBook: **Day close → Import from register → agent key**
   (or ask support) to issue the store's agent key. It is shown
   exactly once.
4. Copy `agent.ini.example` to `agent.ini` and fill in:
   - `api_url` — `https://dinerobook.com`
   - `agent_key` — the `pak_…` value from step 3
   - `watch_dir` — Passport's XML outbox, typically
     `C:\Passport\XMLGateway\BOOutbox` (the same share other
     back-office systems read).
5. Test run in a console:
   `python dinerobook_agent.py --config agent.ini --verbose`
   — you should see files uploading, then "already on server" on
   a re-run (uploads are idempotent).
6. Make it a service — either:
   - **Task Scheduler**: new task, run at startup + on failure
     restart, action `python C:\DineroBook\agent\dinerobook_agent.py
     --config C:\DineroBook\agent\agent.ini`, or
   - **NSSM**: `nssm install DineroBookAgent ...` for a proper
     Windows service.

## Day-to-day

- Files upload within seconds of Passport writing them; the day
  shows up under **Day close → Import from register → staged days**
  and can be booked with one click once your department codes are
  mapped (a one-time setup).
- `uploaded.txt` (next to the script) remembers what's been sent.
  Deleting it is safe — the server ignores duplicates.
- Revoking the key in DineroBook stops the agent instantly; issue
  a new key and update `agent.ini` to resume.
