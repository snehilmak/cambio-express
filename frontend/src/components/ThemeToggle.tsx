import { useState } from "react";

import { updateProfile } from "../api/account";
import { applyTheme, getCurrentTheme, type Theme } from "../lib/theme";
import styles from "./ThemeToggle.module.css";

// Topbar button that flips dark ↔ light.
//
// Renders an icon-only sun / moon in the chrome. Click flips:
//   1. The DOM attribute (instant — CSS picks it up).
//   2. The localStorage cache (so a reload keeps it).
//   3. The server-side User.theme_preference (PUT /auth/profile)
//      so the choice follows the user to other devices.
//
// We optimistically flip first and let the PUT race in the
// background. The server is the authority on next page load, but
// a network blip shouldn't make the click feel laggy.

export default function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(getCurrentTheme);

  function onToggle() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    applyTheme(next);
    // Fire-and-forget. If it fails the local + DOM state still
    // reflect the click; we'd surface a real error only on the
    // /settings/profile page where the dropdown shows the value.
    void updateProfile({ theme_preference: next }).catch(() => {
      /* swallow — see comment above */
    });
  }

  const label = theme === "dark"
    ? "Switch to light mode"
    : "Switch to dark mode";

  return (
    <button
      type="button"
      onClick={onToggle}
      aria-label={label}
      title={label}
      className={styles.button}
    >
      {theme === "dark" ? <SunIcon /> : <MoonIcon />}
    </button>
  );
}

function SunIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round"
      strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2" />
      <path d="M12 20v2" />
      <path d="m4.93 4.93 1.41 1.41" />
      <path d="m17.66 17.66 1.41 1.41" />
      <path d="M2 12h2" />
      <path d="M20 12h2" />
      <path d="m4.93 19.07 1.41-1.41" />
      <path d="m17.66 6.34 1.41-1.41" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round"
      strokeLinejoin="round" aria-hidden="true">
      <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z" />
    </svg>
  );
}
