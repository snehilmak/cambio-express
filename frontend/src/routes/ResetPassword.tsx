import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { AuthChrome, StatusPill } from "../components/AuthChrome";
import { Alert, Button, ButtonLink, Field, Input } from "../components/ui";
import { resetPassword } from "../api/account";
import { ApiError } from "../lib/api";
import styles from "./auth.module.css";

// /app/reset-password?token=… — consume a one-time token to set
// a new password. Token comes from the email link.
export default function ResetPassword() {
  const [sp] = useSearchParams();
  const navigate = useNavigate();
  const token = sp.get("token") ?? "";
  const [pw,      setPw]      = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy,    setBusy]    = useState(false);
  const [error,   setError]   = useState<string | null>(null);
  const [done,    setDone]    = useState(false);

  useEffect(() => {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js").catch(() => {});
    }
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (pw !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    if (pw.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    setBusy(true);
    try {
      await resetPassword({
        token,
        new_password: pw,
        confirm_password: confirm,
      });
      setDone(true);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Could not reset password. The link may be expired.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthChrome navLink={{ to: "/login", label: "← Back to sign in" }}>
      {!token ? (
        <>
          <StatusPill tone="error">LINK MISSING</StatusPill>
          <div className={styles.cardTitle}>Reset link missing</div>
          <div className={styles.cardSub}>
            This link doesn't include a token. Request a new reset link
            and we'll email you a fresh one.
          </div>
          <ButtonLink to="/forgot-password" tone="primary" size="lg" style={{ width: "100%" }}>
            Request a new link
          </ButtonLink>
          <Link to="/login" className={styles.backLink}>← Back to sign in</Link>
        </>
      ) : done ? (
        <>
          <StatusPill>✓ PASSWORD UPDATED</StatusPill>
          <div className={styles.cardTitle}>Password updated</div>
          <div className={styles.cardSub}>
            You can now sign in with your new password.
          </div>
          <Button
            tone="primary"
            size="lg"
            style={{ width: "100%" }}
            onClick={() => navigate("/login")}
          >
            Sign in →
          </Button>
        </>
      ) : (
        <>
          <StatusPill>SET A NEW PASSWORD</StatusPill>
          <div className={styles.cardTitle}>Set a new password</div>
          <div className={styles.cardSub}>Choose something at least 8 characters long.</div>

          <form onSubmit={onSubmit} style={{ display: "flex", flexDirection: "column", gap: "0.95rem" }}>
            {error && <Alert tone="error">{error}</Alert>}

            <Field label="New password">
              <Input
                type="password"
                autoComplete="new-password"
                minLength={8}
                placeholder="Min. 8 characters"
                value={pw}
                onChange={(e) => setPw(e.target.value)}
                disabled={busy}
                required
                autoFocus
              />
            </Field>
            <Field label="Confirm new password">
              <Input
                type="password"
                autoComplete="new-password"
                minLength={8}
                placeholder="Repeat"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                disabled={busy}
                required
              />
            </Field>
            <Button
              type="submit"
              tone="primary"
              size="lg"
              busy={busy}
              disabled={busy || !pw || !confirm}
              style={{ width: "100%" }}
            >
              {busy ? "Saving…" : "Update password"}
            </Button>
          </form>
          <Link to="/login" className={styles.backLink}>← Back to sign in</Link>
        </>
      )}
    </AuthChrome>
  );
}
