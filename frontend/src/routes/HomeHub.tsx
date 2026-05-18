import { useMemo } from "react";
import { Link } from "react-router-dom";

import { filterNavForRole } from "../components/navConfig";
import { type NavItem } from "../components/SlimSidebar";
import { getCurrentIdentity } from "../lib/auth";
import { topVisited } from "../lib/recency";
import { PageHeader, PageShell, Section } from "../components/ui";
import styles from "./HomeHub.module.css";

// /app/home — tile-hub landing.  Every nav item the current
// role can reach is rendered as a colored tile, grouped by
// section (Daily · Finance · Owner · Platform · Account).  A
// "Most Used" strip at the top auto-surfaces the routes the
// user clicks the most so they don't have to dig through the
// fly-out panels for their day-to-day work.
//
// Per-device, localStorage-backed.  Recency is recorded by an
// effect in AppShell whenever ``location.pathname`` changes; the
// strip reads back the top N entries and intersects them with
// the role-eligible items so a demoted user doesn't see admin
// shortcuts in their strip.

const MOST_USED_LIMIT = 6;

export default function HomeHub() {
  const identity = getCurrentIdentity();
  const role = identity?.role ?? "";
  const groups = useMemo(() => filterNavForRole(role), [role]);

  // Build a flat (path → item) map across every group so the
  // "Most Used" strip can recover the icon + label from a
  // recorded path.  Recomputes only when role changes.
  const flatByPath = useMemo(() => {
    const map = new Map<string, NavItem>();
    for (const g of groups) {
      for (const item of g.items) {
        map.set(item.to, item);
      }
    }
    return map;
  }, [groups]);

  const mostUsed = useMemo(() => {
    const eligible = new Set(flatByPath.keys());
    return topVisited(eligible, MOST_USED_LIMIT)
      .map((entry) => ({
        item:  flatByPath.get(entry.path)!,
        count: entry.count,
      }))
      .filter((e) => e.item !== undefined);
  }, [flatByPath]);

  return (
    <PageShell maxWidth="80rem">
      <PageHeader
        title="Home"
        subtitle="Everything you can do, one tap away. Recents on top."
      />

      {mostUsed.length > 0 && (
        <Section>
          <div className={styles.mostUsedStrip}>
            <div className={styles.sectionHeader}>
              <span className={styles.sectionHeaderIcon}>{iconStar()}</span>
              Most used
            </div>
            <div className={styles.tileGrid}>
              {mostUsed.map(({ item, count }) => (
                <Link
                  key={item.to}
                  to={item.to}
                  className={`${styles.tile} ${styles.mostUsedTile}`}
                >
                  <span className={styles.tileIcon}>{item.icon}</span>
                  <span>{item.label}</span>
                  <span className={styles.tileCount}>
                    {count === 1 ? "1 visit" : `${count} visits`}
                  </span>
                </Link>
              ))}
            </div>
          </div>
        </Section>
      )}

      {groups.map((group) => (
        <Section key={group.title}>
          <div className={styles.section}>
            <div className={styles.sectionHeader}>
              <span className={styles.sectionHeaderIcon}>{group.icon}</span>
              {group.title}
            </div>
            <div className={styles.tileGrid}>
              {group.items.map((item) => (
                <Link
                  key={item.to}
                  to={item.to}
                  className={styles.tile}
                >
                  <span className={styles.tileIcon}>{item.icon}</span>
                  <span>{item.label}</span>
                </Link>
              ))}
            </div>
          </div>
        </Section>
      ))}
    </PageShell>
  );
}

function iconStar() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round"
      strokeLinejoin="round" aria-hidden="true">
      <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
    </svg>
  );
}

