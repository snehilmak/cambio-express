"""Flask CLI commands — operator-facing maintenance + cron entrypoints.

Registered onto the Flask app via ``register(app, db)``. Each one
opens its own SessionLocal (or uses the request-scoped session
where appropriate) and delegates to a Service.

Available commands (run via ``flask <name>``):

  purge-expired-stores     Daily — drop cancelled stores past 180d.
  send-trial-reminders     Daily — email expiring-soon trial stores.
  broadcast-announcement   On-demand — re-send an announcement email.
  reset-superadmin         Manual — recover a locked-out superadmin.
  seed-amazon-reviewer     Manual — provision the Fire TV reviewer
                           sandbox account.
"""
from __future__ import annotations

import click


def register(app, db):
    """Wire every operator CLI command onto the Flask `app`."""
    from api.Modules.Auth.Models import RecoveryCode
    from api.Modules.Tenancy.Models import User

    @app.cli.command("purge-expired-stores")
    def _purge_expired_stores_cmd():
        """Delete inactive stores past their retention deadline. Run daily."""
        from api.Core.Database import SessionLocal
        from api.Modules.Billing.Services import purge_expired_stores as _svc
        with SessionLocal() as s:
            n = _svc(s)
        print(f"Purged {n} expired store(s).")

    @app.cli.command("send-trial-reminders")
    def _send_trial_reminders_cmd():
        """Email admins/owners of stores in expiring_soon. Run daily."""
        from api.Core.Database import SessionLocal
        from api.Modules.Notifications.Services.trial_reminders import run as _run
        with SessionLocal() as s:
            n = _run(s)
        print(f"Sent {n} trial reminder email(s).")

    @app.cli.command("broadcast-announcement")
    @click.argument("announcement_id", type=int)
    def _broadcast_announcement_cmd(announcement_id):
        """Resend an announcement email (no-op if already broadcast)."""
        from api.Core.Database import SessionLocal
        from api.Modules.Notifications.Services.broadcasts import run as _run
        with SessionLocal() as s:
            n = _run(s, announcement_id)
        print(f"Broadcast announcement {announcement_id}: {n} email(s) sent.")

    @app.cli.command("reset-superadmin")
    @click.argument("username", required=False)
    @click.option("--reset-2fa", is_flag=True,
                  help="Also wipe TOTP secret + recovery codes.")
    def _reset_superadmin_cmd(username, reset_2fa):
        """Recover a locked-out superadmin from the Render shell.
        /forgot-password intentionally skips this role."""
        q = db.session.query(User).filter_by(role="superadmin")
        if username:
            q = q.filter_by(username=username.strip())
        sa = q.first()
        if not sa:
            click.echo("No superadmin found" +
                       (f" with username={username!r}." if username else "."))
            return
        click.echo(f"Resetting password for superadmin: {sa.username}")
        pw = click.prompt("New password", hide_input=True, confirmation_prompt=True)
        if len(pw) < 8:
            click.echo("Password must be at least 8 characters. Aborting.")
            return
        sa.set_password(pw)
        if reset_2fa:
            sa.totp_secret = None
            sa.totp_enrolled_at = None
            db.session.query(RecoveryCode).filter_by(user_id=sa.id).delete()
            click.echo("2FA wiped — re-enrollment will be forced on next login.")
        db.session.commit()
        click.echo("Done.")

    @app.cli.command("seed-amazon-reviewer")
    @click.option("--password", default=None,
                  help="Override the auto-generated password (>= 12 chars). "
                       "Omit to generate a fresh URL-safe random.")
    @click.option("--keep-data", is_flag=True,
                  help="Don't reseed sample countries/banks/rates if any "
                       "already exist — useful for in-place password rotation.")
    def _seed_amazon_reviewer_cmd(password, keep_data):
        """Delegate to the standalone script's main()."""
        from scripts.seed_amazon_reviewer import main as _main
        argv: list[str] = []
        if password is not None:
            argv += ["--password", password]
        if keep_data:
            argv.append("--keep-data")
        rc = _main(argv)
        if rc != 0:
            raise click.Abort()
