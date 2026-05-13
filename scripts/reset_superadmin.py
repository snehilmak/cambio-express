"""Reset a superadmin's password (and optionally their 2FA).

Run from the Render shell when a superadmin gets locked out. The
``/forgot-password`` self-service flow intentionally skips the
superadmin role, so this is the canonical recovery path. Prompts
for the new password interactively; doesn't touch non-superadmin
accounts.

Invocation::

    python -m scripts.reset_superadmin                  # picks the only superadmin
    python -m scripts.reset_superadmin <username>       # disambiguate by username
    python -m scripts.reset_superadmin --reset-2fa      # also wipe TOTP + recovery codes

Replaces the legacy ``flask reset-superadmin`` CLI. Same behaviour;
no Flask boot.
"""
from __future__ import annotations

import argparse
import getpass
import sys

from api.Core.Database import SessionLocal
from api.Modules.Auth.Models import RecoveryCode
from api.Modules.Tenancy.Models import User


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reset a superadmin's password (and optionally 2FA).",
    )
    parser.add_argument(
        "username", nargs="?",
        help="Disambiguate by username; omit if there's only one superadmin.",
    )
    parser.add_argument(
        "--reset-2fa", action="store_true",
        help="Also wipe TOTP secret + recovery codes, forcing fresh enrollment.",
    )
    args = parser.parse_args(argv)

    with SessionLocal() as session:
        q = session.query(User).filter_by(role="superadmin")
        if args.username:
            q = q.filter_by(username=args.username.strip())
        sa = q.first()
        if not sa:
            suffix = f" with username={args.username!r}." if args.username else "."
            print(f"No superadmin found{suffix}")
            return 1

        print(f"Resetting password for superadmin: {sa.username}")
        pw = getpass.getpass("New password: ")
        confirm = getpass.getpass("Confirm new password: ")
        if pw != confirm:
            print("Passwords don't match. Aborting.")
            return 1
        if len(pw) < 8:
            print("Password must be at least 8 characters. Aborting.")
            return 1

        sa.set_password(pw)
        if args.reset_2fa:
            sa.totp_secret = None
            sa.totp_enrolled_at = None
            session.query(RecoveryCode).filter_by(user_id=sa.id).delete()
            print("2FA wiped — re-enrollment will be forced on next login.")
        session.commit()
        print("Done.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
