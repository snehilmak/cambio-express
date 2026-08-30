import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { AuthChrome, StatusPill } from "../components/AuthChrome";
import { Button, Field, Input } from "../components/ui";
import { forgotPassword } from "../api/account";
import styles from "./auth.module.css";

// /app/forgot-password — request a reset link.
//
// Per CLAUDE.md security invariant #10 the response is always
// "Check your email" regardless of whether the address exists,
// so attackers can't enumerate registered emails.
export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [busy,  setBusy]  = useState(false);
  const [done,  setDone]  = useState(false);

  useEffect(() => {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js").catch(() => {});
    }
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await forgotPassword(email.trim());
    } catch {
      // Server responds 200 even on unknown email; flip to success
      // either way so we don't leak whether the address was registered.
    } finally {
      setBusy(false);
      setDone(true);
    }
  }

  return (
    <AuthChrome navLink={{ to: "/login", label: "← Back to sign in" }}>
      {done ? (
        <>
          <StatusPill>✓ EMAIL SENT</StatusPill>
          <div className={styles.cardTitle}>Check your email</div>
          <div className={styles.cardSub}>
            If <span className={styles.subMono}>{email}</span> is registered,
            you'll receive a link to set a new password. The link expires in
            1 hour. If you don't see it, check your spam folder.
          </div>
          <Link to="/login" className={styles.backLink}>← Back to sign in</Link>
        </>
      ) : (
        <>
          <StatusPill>PASSWORD RESET</StatusPill>
          <div className={styles.cardTitle}>Forgot your password?</div>
          <div className={styles.cardSub}>
            Enter the email on your account. We'll send a one-time link
            to set a new password. For employees, contact your store
            admin for a reset.
          </div>
          <form onSubmit={onSubmit} style={{ display: "flex", flexDirection: "column", gap: "0.95rem" }}>
            <Field label="Email">
              <Input
                type="email"
                autoComplete="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={busy}
                required
                autoFocus
              />
            </Field>
            <Button
              type="submit"
              tone="primary"
              size="lg"
              busy={busy}
              disabled={busy || !email}
              style={{ width: "100%" }}
            >
              {busy ? "Sending…" : "Send reset link"}
            </Button>
          </form>
          <Link to="/login" className={styles.backLink}>← Back to sign in</Link>
        </>
      )}
    </AuthChrome>
  );
}
