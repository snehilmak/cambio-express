import { useEffect, useState, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";

import { sectionSlug } from "./navConfig";
import styles from "./SlimSidebar.module.css";

export interface NavItem {
  to: string;
  label: string;
  icon: ReactNode;
  /** Roles that should see this item. Omit for "everyone authed". */
  roles?: string[];
  /** Required permission as "resource.action". Hidden when missing. */
  perm?: string;
  /** Module flag that must be ON for this store (business-type
   *  bundles — e.g. "module_money_services"). Hidden when off. */
  flag?: string;
  /** One-line description shown under the label on the section-hub
   *  tile grid. Optional — tiles without one render label-only. */
  desc?: string;
}

export interface NavGroup {
  /** Short label that fits under the icon (~10 chars). */
  title: string;
  /** Icon shown in the slim column AND tinted in the fly-out header. */
  icon: ReactNode;
  items: NavItem[];
  /** Roles that should see this group. Omit for "everyone authed". */
  roles?: string[];
  /** When set, the group is a DIRECT LINK: the icon-column button
   *  becomes a NavLink to this path and there is no fly-out / hub.
   *  Use for a section that IS a single destination (e.g. Reports →
   *  the Report Center) rather than a menu of sub-pages. `items`
   *  should be `[]` for a direct-link group. */
  to?: string;
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
  groups, drawerOpen, brandName = "DineroBook", supportLink,
  supportBadge = 0,
}: {
  groups: NavGroup[];
  drawerOpen: boolean;
  brandName?: string;
  supportLink?: NavItem;
  /** Unread count rendered as a phone-style badge circle on the
   *  support button. 0 hides the badge. */
  supportBadge?: number;
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
      {/* Slim icon column — desktop only (CSS hides on mobile).
          Brand is a single ``$`` tile; the wordmark would overflow
          the 4.75rem column and the tile is recognizable on its
          own.  See ``DrawerBrand`` below for the mobile drawer
          where there's room for the full wordmark. */}
      <div className={styles.iconCol}>
        <div
          className={styles.brand}
          title={brandName}
          aria-label={brandName}
        >
          <span className={styles.brandMark}>$</span>
        </div>
        {groups.map((group) => {
          // Direct-link group (e.g. Reports → Report Center): render a
          // NavLink straight to its destination, no fly-out.
          if (group.to) {
            return (
              <NavLink
                key={group.title}
                to={group.to}
                className={({ isActive }) =>
                  `${styles.groupBtn}${isActive ? " " + styles.isActive : ""}`
                }
                title={group.title}
                aria-label={group.title}
              >
                <span className={styles.groupIcon}>{group.icon}</span>
                <span className={styles.groupLabel}>{group.title}</span>
              </NavLink>
            );
          }
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
              aria-haspopup="menu"
              aria-controls={`group-flyout-${group.title.toLowerCase()}`}
              aria-label={`${group.title} menu`}
            >
              <span className={styles.groupIcon}>{group.icon}</span>
              <span className={styles.groupLabel}>{group.title}</span>
            </button>
          );
        })}
        {supportLink && (
          <NavLink
            to={supportLink.to}
            className={({ isActive }) =>
              `${styles.supportBtn}${isActive ? " " + styles.isActive : ""}`
            }
            title={supportLink.label}
            aria-label={
              supportBadge > 0
                ? `${supportLink.label} — ${supportBadge} unread`
                : supportLink.label
            }
          >
            <span className={styles.groupIcon}>{supportLink.icon}</span>
            <span className={styles.groupLabel}>{supportLink.label}</span>
            <UnreadBadge count={supportBadge} />
          </NavLink>
        )}
      </div>

      {/* Fly-out panel — desktop only.  Backdrop is a plain
          div + onClick (not a <button>) so it doesn't grab a
          tab stop or announce itself to screen readers — it's
          purely a click-catcher behind the modal panel.  ESC
          closes the panel via the keydown listener above. */}
      {activeGroup && (
        <>
          <div
            className={styles.flyoutBackdrop}
            onClick={() => setOpenGroup(null)}
            aria-hidden="true"
          />
          <div
            id={`group-flyout-${activeGroup.title.toLowerCase()}`}
            className={styles.flyoutPanel}
            role="menu"
          >
            {/* Header doubles as a link into the section's tile
                hub — the fast list stays below for repeat nav, the
                header opens the polished "pick where to go" grid. */}
            <NavLink
              to={`/hub/${sectionSlug(activeGroup.title)}`}
              className={styles.flyoutHeader}
              role="menuitem"
              title={`Open the ${activeGroup.title} hub`}
            >
              <span className={styles.flyoutHeaderIcon}>
                {activeGroup.icon}
              </span>
              <span className={styles.flyoutHeaderTitle}>
                {activeGroup.title}
              </span>
              <span className={styles.flyoutHeaderChevron} aria-hidden="true">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
                  stroke="currentColor" strokeWidth="2" strokeLinecap="round"
                  strokeLinejoin="round">
                  <rect x="3" y="3" width="7" height="7" rx="1.5" />
                  <rect x="14" y="3" width="7" height="7" rx="1.5" />
                  <rect x="3" y="14" width="7" height="7" rx="1.5" />
                  <rect x="14" y="14" width="7" height="7" rx="1.5" />
                </svg>
              </span>
            </NavLink>
            <div className={styles.itemList}>
              {activeGroup.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    `${styles.itemRow}${isActive ? " " + styles.isActive : ""}`
                  }
                  end={false}
                  role="menuitem"
                >
                  <span className={styles.itemIcon}>{item.icon}</span>
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
            {/* Direct-link group: the title IS the destination, no
                /hub landing and no sub-item list. */}
            <NavLink
              to={group.to ?? `/hub/${sectionSlug(group.title)}`}
              className={group.to
                ? ({ isActive }) =>
                    `${styles.itemRow}${isActive ? " " + styles.isActive : ""}`
                : styles.drawerGroupTitle}
            >
              {group.to
                ? <><span className={styles.itemIcon}>{group.icon}</span><span>{group.title}</span></>
                : group.title}
            </NavLink>
            <div className={styles.itemList}>
              {group.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    `${styles.itemRow}${isActive ? " " + styles.isActive : ""}`
                  }
                  end={false}
                >
                  <span className={styles.itemIcon}>{item.icon}</span>
                  <span>{item.label}</span>
                </NavLink>
              ))}
            </div>
          </div>
        ))}
        {supportLink && (
          <div className={styles.drawerGroup}>
            <NavLink
              to={supportLink.to}
              className={({ isActive }) =>
                `${styles.itemRow}${isActive ? " " + styles.isActive : ""}`
              }
            >
              <span className={styles.itemIcon}>{supportLink.icon}</span>
              <span>{supportLink.label}</span>
              <UnreadBadge count={supportBadge} inline />
            </NavLink>
          </div>
        )}
      </div>
    </aside>
  );
}

/** Phone-style red notification circle. Hidden at 0; caps the
 *  display at 99+ so the circle never stretches. `inline` renders
 *  it in the row flow (mobile drawer) instead of pinned to the
 *  icon corner (desktop slim column). */
function UnreadBadge({ count, inline }: { count: number; inline?: boolean }) {
  if (count <= 0) return null;
  return (
    <span
      className={inline ? styles.badgeInline : styles.badge}
      aria-hidden="true"
    >
      {count > 99 ? "99+" : count}
    </span>
  );
}
