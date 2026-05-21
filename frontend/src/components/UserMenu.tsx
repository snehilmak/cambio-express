import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import type { getCurrentIdentity } from "../lib/auth";
import styles from "./UserMenu.module.css";

// Topbar user menu — circular avatar button → fade-scale-in
// dropdown with Profile / Notifications / Sign out. Mirrors the
// legacy Jinja `base.html` chrome (PR pre-SPA-migration) where
// the avatar dropdown was the only entry point to the per-user
// account screens.
//
// Click outside / Escape closes the menu. The menu uses CSS-based
// fade-scale-in animation via the `.ds-popover` class from
// `components/ui/ui.css` — honors `prefers-reduced-motion`
// automatically through the global rule in `static/content.css`.

type Identity = ReturnType<typeof getCurrentIdentity>;

export function UserMenu({
  identity, onSignOut,
}: {
  identity: Identity;
  onSignOut: () => void;
}) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  // Click-outside-to-close. Wrap-ref covers both the avatar
  // button and the dropdown panel since they share a parent.
  useEffect(() => {
    if (!open) return;
    function onDocClick(e: MouseEvent) {
      if (!wrapRef.current) return;
      if (!wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const username = identity?.username || "";
  const initial = (username[0] || "·").toUpperCase();
  const role = identity?.role || "";

  return (
    <div className={styles.wrap} ref={wrapRef}>
      <button
        type="button"
        className={styles.avatarBtn}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`User menu for ${username || "current user"}`}
        onClick={() => setOpen((v) => !v)}
      >
        <span className={styles.avatar}>{initial}</span>
      </button>
      {open && (
        <div className={`${styles.dropdown} ds-popover`} role="menu">
          <div className={styles.identityRow}>
            <div className={styles.username}>{username || "—"}</div>
            {role && (
              <div className={styles.rolePill}>{role}</div>
            )}
          </div>
          <div className={styles.divider} />
          <Link
            to="/settings/profile"
            className={styles.item}
            role="menuitem"
            onClick={() => setOpen(false)}
          >
            <ProfileIcon />
            <span>Profile</span>
          </Link>
          <Link
            to="/account/notifications"
            className={styles.item}
            role="menuitem"
            onClick={() => setOpen(false)}
          >
            <BellIcon />
            <span>Notifications</span>
          </Link>
          <div className={styles.divider} />
          <button
            type="button"
            className={`${styles.item} ${styles.signOut}`}
            role="menuitem"
            onClick={() => {
              setOpen(false);
              onSignOut();
            }}
          >
            <SignOutIcon />
            <span>Sign out</span>
          </button>
        </div>
      )}
    </div>
  );
}

function ProfileIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
         stroke="currentColor" strokeWidth="2" strokeLinecap="round"
         strokeLinejoin="round" aria-hidden>
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </svg>
  );
}

function BellIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
         stroke="currentColor" strokeWidth="2" strokeLinecap="round"
         strokeLinejoin="round" aria-hidden>
      <path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.73 21a2 2 0 0 1-3.46 0" />
    </svg>
  );
}

function SignOutIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
         stroke="currentColor" strokeWidth="2" strokeLinecap="round"
         strokeLinejoin="round" aria-hidden>
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <polyline points="16 17 21 12 16 7" />
      <line x1="21" y1="12" x2="9" y2="12" />
    </svg>
  );
}
