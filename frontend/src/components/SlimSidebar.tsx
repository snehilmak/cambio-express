import { useEffect, useState, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";

import styles from "./SlimSidebar.module.css";

export interface NavItem {
  to: string;
  label: string;
  icon: ReactNode;
  /** Roles that should see this item. Omit for "everyone authed". */
  roles?: string[];
}

export interface NavGroup {
  /** Short label that fits under the icon (~10 chars). */
  title: string;
  /** Icon shown in the slim column AND tinted in the fly-out header. */
  icon: ReactNode;
  items: NavItem[];
  /** Roles that should see this group. Omit for "everyone authed". */
  roles?: string[];
}


/** Slim icon-only sidebar + click-to-open fly-out panel.
 *
 *  Desktop layout: 4.75rem column on the left with one button per
 *  group. Click → fly-out panel slides in showing that group's
 *  items as colored tiles. The panel closes on click-outside,
 *  ESC, or when the route changes (so picking a tile auto-closes).
 *
 *  Mobile (<768px): the AppShell hamburger opens a drawer that
 *  renders the same nav data as a single scrollable column with
 *  the groups stacked. No fly-out, no cramped icons.
 *
 *  ``drawerOpen`` is the mobile-drawer flag from AppShell — passed
 *  through so the component owns its own ``app-sidebar`` class
 *  (the drawer slide animation lives in the legacy styles.css
 *  rules for backwards compat with the existing transitions). */
export function SlimSidebar({
  groups, drawerOpen, brandName = "DineroBook",
}: {
  groups: NavGroup[];
  drawerOpen: boolean;
  brandName?: string;
}) {
  const location = useLocation();
  const [openGroup, setOpenGroup] = useState<string | null>(null);

  // Auto-close the fly-out on route change — picking a tile
  // should land you on the new page with a clean chrome.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- close fly-out when the router navigates; pathname comes from outside React state
    setOpenGroup(null);
  }, [location.pathname]);

  // ESC closes the fly-out (matches the modal pattern across the SPA).
  useEffect(() => {
    if (openGroup === null) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpenGroup(null);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [openGroup]);

  const activeGroup = openGroup
    ? groups.find((g) => g.title === openGroup) ?? null
    : null;

  return (
    <aside
      className={`app-sidebar${drawerOpen ? " is-open" : ""}`}
      aria-label="Primary navigation"
    >
      {/* Slim icon column — desktop only (CSS hides on mobile). */}
      <div className={styles.iconCol}>
        <div className={styles.brand}>
          <span className={styles.brandMark}>$</span>
          <span className={styles.brandName}>{brandName.toUpperCase()}</span>
        </div>
        {groups.map((group) => {
          const isActive = openGroup === group.title
            || group.items.some((i) => location.pathname.startsWith(i.to));
          return (
            <button
              key={group.title}
              type="button"
              className={`${styles.groupBtn}${isActive ? " " + styles.isActive : ""}`}
              onClick={() => setOpenGroup(
                openGroup === group.title ? null : group.title,
              )}
              aria-expanded={openGroup === group.title}
              aria-label={`${group.title} menu`}
            >
              <span className={styles.groupIcon}>{group.icon}</span>
              <span className={styles.groupLabel}>{group.title}</span>
            </button>
          );
        })}
      </div>

      {/* Fly-out panel — desktop only. */}
      {activeGroup && (
        <>
          <button
            type="button"
            className={styles.flyoutBackdrop}
            aria-label="Close menu"
            onClick={() => setOpenGroup(null)}
          />
          <div className={styles.flyoutPanel} role="menu">
            <div className={styles.flyoutHeader}>{activeGroup.title}</div>
            <div className={styles.tileGrid}>
              {activeGroup.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    `${styles.tile}${isActive ? " " + styles.isActive : ""}`
                  }
                  end={false}
                  role="menuitem"
                >
                  <span className={styles.tileIcon}>{item.icon}</span>
                  <span>{item.label}</span>
                </NavLink>
              ))}
            </div>
          </div>
        </>
      )}

      {/* Mobile drawer — the AppShell hamburger flips
          ``.app-sidebar`` ``.is-open``; CSS hides the icon column +
          fly-out and shows this drawer block instead. */}
      <div className={styles.drawer}>
        <div className={styles.drawerBrand}>
          <span className={styles.brandMark}>$</span>
          <span className={styles.drawerBrandName}>{brandName}</span>
        </div>
        {groups.map((group) => (
          <div key={group.title} className={styles.drawerGroup}>
            <div className={styles.drawerGroupTitle}>{group.title}</div>
            <div className={styles.tileGrid}>
              {group.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    `${styles.tile}${isActive ? " " + styles.isActive : ""}`
                  }
                  end={false}
                >
                  <span className={styles.tileIcon}>{item.icon}</span>
                  <span>{item.label}</span>
                </NavLink>
              ))}
            </div>
          </div>
        ))}
      </div>
    </aside>
  );
}
