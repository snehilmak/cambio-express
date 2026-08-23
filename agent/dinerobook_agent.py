"""DineroBook site agent — Gilbarco journal watcher.

Watches the folder where Gilbarco Passport writes its NAXML
journal files (PJR*.xml) and pushes each new file to the
DineroBook API the moment it lands. Deliberately dumb by design:
no parsing, no XML knowledge — the server does all of that, so
this script almost never needs an update.

Python 3.9+ standard library only — no pip installs at the site.

    python dinerobook_agent.py --config agent.ini

Config (agent.ini):

    [agent]
    api_url    = https://dinerobook.com
    agent_key  = pak_...            ; issued in DineroBook, shown once
    watch_dir  = C:\\Passport\\XMLGateway\\BOOutbox
    pattern    = PJR*.xml
    poll_seconds = 5

State: a plain text file (uploaded.txt next to this script) lists
filenames already accepted by the server, so restarts never
re-upload (the server is idempotent anyway — this just saves
bandwidth). Delete the file to force a full re-send.

Run it as a Windows service via Task Scheduler ("At startup",
restart on failure) or NSSM. See agent/README.md.
"""
from __future__ import annotations

import argparse
import base64
import configparser
import fnmatch
import json
import logging
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

log = logging.getLogger("dinerobook-agent")

UPLOAD_PATH = "/api/v2/posimport/agent/upload"
# Files can still be mid-write when first seen — require the size
# to hold still for one poll before uploading.
MAX_FILE_BYTES = 4 * 1024 * 1024
RETRY_BACKOFF_SECONDS = (5, 15, 60, 300)


def load_config(path: str) -> dict:
    parser = configparser.ConfigParser()
    if not parser.read(path):
        sys.exit(f"Config file not found: {path}")
    section = parser["agent"]
    return {
        "api_url": section.get("api_url", "").rstrip("/"),
        "agent_key": section.get("agent_key", ""),
        "watch_dir": section.get("watch_dir", ""),
        "pattern": section.get("pattern", "PJR*.xml"),
        "poll_seconds": section.getint("poll_seconds", 5),
    }


class UploadedLedger:
    """Filenames the server has already accepted."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._names: set[str] = set()
        if path.exists():
            self._names = {
                line.strip()
                for line in path.read_text().splitlines()
                if line.strip()
            }

    def __contains__(self, name: str) -> bool:
        return name in self._names

    def add(self, name: str) -> None:
        self._names.add(name)
        with self._path.open("a") as f:
            f.write(name + "\n")


def upload(cfg: dict, path: Path) -> bool:
    """Push one file. True = server accepted (staged or known
    duplicate); False = retry later."""
    content = path.read_bytes()
    if len(content) > MAX_FILE_BYTES:
        log.warning("skipping %s: too large (%d bytes)", path.name, len(content))
        return True   # never going to succeed — don't retry forever
    body = json.dumps({
        "filename": path.name,
        "content_base64": base64.b64encode(content).decode(),
    }).encode()
    request = urllib.request.Request(
        cfg["api_url"] + UPLOAD_PATH,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Agent-Key": cfg["agent_key"],
            "User-Agent": "dinerobook-agent/1.0",
        },
        method="POST",
    )
    for delay in (0,) + RETRY_BACKOFF_SECONDS:
        if delay:
            time.sleep(delay)
        try:
            with urllib.request.urlopen(request, timeout=30) as resp:
                data = json.loads(resp.read().decode())
                if data.get("parse_error"):
                    log.warning(
                        "%s staged with parse error: %s",
                        path.name, data["parse_error"],
                    )
                elif data.get("duplicate"):
                    log.info("%s already on server", path.name)
                else:
                    log.info(
                        "%s uploaded (business day %s)",
                        path.name, data.get("business_date"),
                    )
                return True
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                log.error("agent key rejected — fix agent.ini and restart")
                time.sleep(300)
                return False
            if exc.code == 422:
                log.warning("%s rejected by server (422) — skipping", path.name)
                return True
            log.warning("%s: HTTP %s — will retry", path.name, exc.code)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            log.warning("%s: %s — will retry", path.name, exc)
    return False


def watch(cfg: dict) -> None:
    watch_dir = Path(cfg["watch_dir"])
    if not watch_dir.is_dir():
        sys.exit(f"Watch directory not found: {watch_dir}")
    ledger = UploadedLedger(Path(__file__).with_name("uploaded.txt"))
    log.info(
        "watching %s for %s (every %ss)",
        watch_dir, cfg["pattern"], cfg["poll_seconds"],
    )
    pending_sizes: dict[str, int] = {}
    while True:
        try:
            for path in sorted(watch_dir.iterdir()):
                name = path.name
                if not fnmatch.fnmatch(name, cfg["pattern"]):
                    continue
                if name in ledger:
                    continue
                size = path.stat().st_size
                # Wait until the size holds still across two polls —
                # Passport may still be writing the file.
                if pending_sizes.get(name) != size:
                    pending_sizes[name] = size
                    continue
                if upload(cfg, path):
                    ledger.add(name)
                    pending_sizes.pop(name, None)
        except Exception:            # noqa: BLE001 — a watcher must not die
            log.exception("watch loop error — continuing")
        time.sleep(cfg["poll_seconds"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="agent.ini")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    cfg = load_config(args.config)
    for field in ("api_url", "agent_key", "watch_dir"):
        if not cfg[field]:
            sys.exit(f"agent.ini is missing [agent] {field}")
    watch(cfg)


if __name__ == "__main__":
    main()
