import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import type { getCurrentIdentity } from "../lib/auth";
import styles from "./UserMenu.module.css";

// Topbar user menu — circular avatar button → fade-scale-in
// dropdown with Profile / Notifications / Sign out. Mirrors the
// legacy Jinja `base.html` chrome (PR pre-SPA-migration) where
// the avatar dropdown was the only entry point to the per-user
// account screens.
//
// Built on Radix DropdownMenu (UI-STANDARDS §5: overlay behavior
// comes from a headless primitive, never hand-rolled) — Radix
// owns outside-click, Escape, focus return, and arrow-key
// navigation. The panel keeps the CSS fade-scale-in via the
// `.ds-popover` class from `components/ui/ui.css`, which honors
// `prefers-reduced-motion` through the global rule in
// `static/content.css`.

type Identity = ReturnType<typeof getCurrentIdentity>;

export function UserMenu({
  identity, onSignOut,
}: {
  identity: Identity;
  onSignOut: () => void;
}) {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();

  const username = identity?.username || "";
  const initial = (username[0] || "·").toUpperCase();
  const role = identity?.role || "";

  return (
    <DropdownMenu.Root open={open} onOpenChange={setOpen}>
      <DropdownMenu.Trigger asChild>
        <button
          type="button"
          className={styles.avatarBtn}
          aria-label={`User menu for ${username || "current user"}`}
        >
          <span className={styles.avatar}>{initial}</span>
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          className={`${styles.dropdown} ds-popover`}
          align="end"
          sideOffset={6}
        >
          <div className={styles.identityRow}>
            <div className={styles.username}>{username || "—"}</div>
            {role && (
              <div className={styles.rolePill}>{role}</div>
            )}
          </div>
          <DropdownMenu.Separator className={styles.divider} />
          <DropdownMenu.Item
            className={styles.item}
            onSelect={() => navigate("/settings/profile")}
          >
            <ProfileIcon />
            <span>Profile</span>
          </DropdownMenu.Item>
          <DropdownMenu.Item
            className={styles.item}
            onSelect={() => navigate("/account/notifications")}
          >
            <BellIcon />
            <span>Notifications</span>
          </DropdownMenu.Item>
          <DropdownMenu.Separator className={styles.divider} />
          <DropdownMenu.Item
            className={`${styles.item} ${styles.signOut}`}
            onSelect={onSignOut}
          >
            <SignOutIcon />
            <span>Sign out</span>
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
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
