import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";

import styles from "./Tabs.module.css";

/** Horizontal tab bar for splitting long pages into logical areas.
 *
 *  Two flavors:
 *
 *  ```tsx
 *  // URL-routed (preferred for top-level admin pages — deep-linkable,
 *  // browser back button works correctly):
 *  <TabsBar>
 *    <TabsLink to="/settings/profile">Profile</TabsLink>
 *    <TabsLink to="/settings/general">General</TabsLink>
 *    <TabsLink to="/settings/billing">Billing</TabsLink>
 *  </TabsBar>
 *  // ...then render <Outlet /> below for the active sub-route.
 *
 *  // Local-state (for in-page tabs that don't deserve their own URL,
 *  // e.g. swappable panels on a dashboard widget):
 *  <TabsBar>
 *    <TabsButton active={tab === "a"} onClick={() => setTab("a")}>A</TabsButton>
 *    <TabsButton active={tab === "b"} onClick={() => setTab("b")}>B</TabsButton>
 *  </TabsBar>
 *  ```
 *
 *  Visual language matches the rest of the kit: hover lightens the
 *  background, active gets a neon underline + neon-tinted text,
 *  `:focus-visible` adds the 2px neon outline.  Horizontal scroll
 *  on overflow so 6+ tabs on a narrow phone don't wrap.
 */
export function TabsBar({ children }: { children: ReactNode }) {
  return (
    <nav className={styles.bar} role="tablist">
      {children}
    </nav>
  );
}


/** URL-routed tab.  Wraps NavLink so React Router computes the
 *  active state automatically based on the current pathname. */
export function TabsLink({
  to, children, end = false,
}: {
  to: string;
  children: ReactNode;
  /** Pass `end` for tabs whose URL is a prefix of another tab's URL
   *  (e.g. an "Overview" tab at `/foo` would otherwise match every
   *  `/foo/*` sub-route).  Defaults to false to match React Router 7
   *  NavLink behavior. */
  end?: boolean;
}) {
  return (
    <NavLink
      to={to}
      end={end}
      role="tab"
      className={({ isActive }) =>
        `${styles.tab}${isActive ? " " + styles.isActive : ""}`
      }
    >
      {children}
    </NavLink>
  );
}


/** Local-state tab.  Use when the URL shouldn't change between
 *  panels (in-page widget tabs, etc.). */
export function TabsButton({
  active, onClick, children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={`${styles.tab}${active ? " " + styles.isActive : ""}`}
    >
      {children}
    </button>
  );
}
