import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";

import { AuthChrome } from "../components/AuthChrome";
import { signupOwner } from "../api/account";
import { ApiError } from "../lib/api";
import { setAccessToken } from "../lib/auth";
import styles from "./auth.module.css";

// Multi-store owner signup at /app/signup/owner. Creates the owner
// user + JWT; the owner connects/redeems individual store codes
// later through the dashboard.
export default function SignupOwner() {
  const navigate = useNavigate();
  const [fullName, setFullName] = useState("");
  const [email,    setEmail]    = useState("");
  const [password, setPassword] = useState("");
  const [busy,     setBusy]     = useState(false);
  const [error,    setError]    = useState<string | null>(null);
  const [errors,   setErrors]   = useState<Record<string, string>>({});

  useEffect(() => {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js").catch(() => {});
    }
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null); setErrors({});
    setBusy(true);
    try {
      const result = await signupOwner({
        full_name: fullName.trim(),
        email:     email.trim(),
        password,
      });
      setAccessToken(result.access_token);
      navigate("/owner/dashboard", { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
        const detail = (err.body as { detail?: { field?: string; message?: string } } | null)?.detail;
        if (detail?.field && detail?.message) {
          setErrors({ [detail.field]: detail.message });
          setError(null);
        }
      } else {
        setError("Could not create account. Please try again.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthChrome navLink={{ to: "/login", label: "Already have an account? Sign in" }}>
      <div className={styles.badgePill}>★ MULTI-STORE OWNER</div>
      <div className={styles.cardTitle}>Create owner account</div>
      <div className={styles.cardSub}>Manage multiple store locations from one login.</div>

      {error && <div className={styles.errorMsg}>{error}</div>}

      <form onSubmit={onSubmit}>
        <OwnerField label="Full Name" error={errors.full_name}>
          <input
            className={`${styles.input}${errors.full_name ? ` ${styles.inputError}` : ""}`}
            type="text"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            placeholder="Your full name"
            disabled={busy}
            required
          />
        </OwnerField>
        <OwnerField label="Email" error={errors.email}>
          <input
            className={`${styles.input}${errors.email ? ` ${styles.inputError}` : ""}`}
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            autoComplete="email"
            disabled={busy}
            required
          />
        </OwnerField>
        <OwnerField label="Password" error={errors.password}>
          <input
            className={`${styles.input}${errors.password ? ` ${styles.inputError}` : ""}`}
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Min. 8 characters"
            autoComplete="new-password"
            minLength={8}
            disabled={busy}
            required
          />
        </OwnerField>
        <button
          type="submit"
          className={`${styles.submitBtn}${busy ? ` ${styles.isBusy}` : ""}`}
          disabled={busy || !fullName || !email || !password}
        >
          {busy ? "Creating account…" : "Create owner account →"}
        </button>
      </form>

      <div className={styles.loginPrompt}>
        Already have an account? <Link to="/login">Sign in</Link>
      </div>
      <div className={styles.loginPrompt} style={{ marginTop: 10 }}>
        Managing a single store? <Link to="/signup">Sign up as a store</Link>
      </div>
    </AuthChrome>
  );
}


function OwnerField({
  label, error, children,
}: { label: string; error?: string; children: ReactNode }) {
  return (
    <div className={styles.field}>
      <label className={styles.label}>{label}</label>
      {children}
      {error && <div className={styles.fieldError}>{error}</div>}
    </div>
  );
}
