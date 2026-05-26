import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Command } from "cmdk";

import { getCurrentIdentity } from "../lib/auth";
import { filterNavForRole } from "./navConfig";
import styles from "./CommandPalette.module.css";

interface CommandItem {
  label: string;
  to: string;
  group: string;
  keywords?: string;
}

function buildItems(role: string): CommandItem[] {
  const groups = filterNavForRole(role);
  const items: CommandItem[] = [];
  for (const g of groups) {
    for (const item of g.items) {
      items.push({
        label: item.label,
        to: item.to,
        group: g.title,
        keywords: `${g.title} ${item.label}`.toLowerCase(),
      });
    }
  }
  return items;
}

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const identity = getCurrentIdentity();
  const items = identity ? buildItems(identity.role) : [];

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      }
      if (e.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  function go(to: string) {
    setOpen(false);
    navigate(to);
  }

  if (!open) return null;

  const grouped = new Map<string, CommandItem[]>();
  for (const item of items) {
    const arr = grouped.get(item.group) ?? [];
    arr.push(item);
    grouped.set(item.group, arr);
  }

  return (
    <div className={styles.overlay} onClick={() => setOpen(false)}>
      <div className={styles.dialog} onClick={(e) => e.stopPropagation()}>
        <Command label="Navigate to…">
          <Command.Input
            className={styles.input}
            placeholder="Search pages, stores, users…"
            autoFocus
          />
          <Command.List className={styles.list}>
            <Command.Empty className={styles.empty}>
              No results found.
            </Command.Empty>
            {Array.from(grouped.entries()).map(([group, groupItems]) => (
              <Command.Group key={group} heading={group} className={styles.groupHeading}>
                {groupItems.map((item) => (
                  <Command.Item
                    key={item.to}
                    value={item.keywords}
                    onSelect={() => go(item.to)}
                    className={styles.item}
                  >
                    <span className={styles.itemIcon}>→</span>
                    {item.label}
                  </Command.Item>
                ))}
              </Command.Group>
            ))}
          </Command.List>
          <div className={styles.footer}>
            <span>
              <span className={styles.kbd}>↑↓</span> navigate
              <span className={styles.kbd}>↵</span> open
              <span className={styles.kbd}>esc</span> close
            </span>
            <span>
              <span className={styles.kbd}>⌘K</span> toggle
            </span>
          </div>
        </Command>
      </div>
    </div>
  );
}
