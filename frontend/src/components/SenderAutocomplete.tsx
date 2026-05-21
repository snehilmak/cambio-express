import { useEffect, useRef, useState } from "react";

import { useCustomerSearch, type CustomerRow } from "../api/customers";
import { fontSize } from "./ui";

// Type-and-pick autocomplete for the sender name on the transfer
// form. Wraps `useCustomerSearch` and a small popover.
//
//  • The visible <input> mirrors the form's sender_name field.
//  • Typing 2+ chars opens a dropdown with up to 8 matches +
//    suggestions from the umbrella's customer directory.
//  • Picking a row calls `onPick(row)` so the parent form can
//    fill phone country / phone / address / dob + remember the
//    customer_id (so the umbrella upsert reuses the same row
//    instead of creating a duplicate).
//  • Continuing to type without picking just updates
//    `sender_name`, the customer_id stays null, and the upsert
//    will fall back to phone-based lookup or create a new row.
//
// Same behavior as the legacy transfer_form.html autocomplete —
// keeps the SPA's UX identical so cashiers don't relearn anything
// during the cutover.

interface Props {
  value: string;
  onChange: (name: string) => void;
  onPick: (row: CustomerRow) => void;
  // Cleared to null when the user types a fresh value after a
  // pick so the upsert lookup falls back to phone-based dedupe
  // (matches legacy form behavior).
  onClearPickedId?: () => void;
  required?: boolean;
}

export default function SenderAutocomplete({
  value, onChange, onPick, onClearPickedId, required,
}: Props) {
  const [open, setOpen] = useState(false);
  const [activeIdx, setActiveIdx] = useState(-1);
  const containerRef = useRef<HTMLDivElement>(null);
  const { data, isFetching } = useCustomerSearch(value);

  // Cap the dropdown so a noisy fuzzy result doesn't dominate
  // the form. 8 is a sweet spot per the legacy autocomplete UX.
  const matches     = (data?.matches ?? []).slice(0, 8);
  const suggestions = (data?.suggestions ?? []).slice(0, 8 - matches.length);
  const all = [...matches, ...suggestions];

  // Close on click-outside.
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (!containerRef.current) return;
      if (!containerRef.current.contains(e.target as Node)) {
        setOpen(false);
        setActiveIdx(-1);
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  function handleKey(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!open || all.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIdx((i) => (i + 1) % all.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIdx((i) => (i - 1 + all.length) % all.length);
    } else if (e.key === "Enter" && activeIdx >= 0) {
      e.preventDefault();
      pick(all[activeIdx]);
    } else if (e.key === "Escape") {
      setOpen(false);
      setActiveIdx(-1);
    }
  }

  function pick(row: CustomerRow) {
    onPick(row);
    setOpen(false);
    setActiveIdx(-1);
  }

  return (
    <div ref={containerRef} style={{ position: "relative" }}>
      <input
        type="text"
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          if (onClearPickedId) onClearPickedId();
          setOpen(true);
          setActiveIdx(-1);
        }}
        onFocus={() => setOpen(value.length >= 2)}
        onKeyDown={handleKey}
        autoComplete="off"
        required={required}
        style={inputStyle}
      />
      {open && value.length >= 2 && (
        <div className="ds-popover" style={popoverStyle}>
          {isFetching && (
            <p style={{ ...rowMutedStyle, padding: "0.6rem 0.85rem" }}>
              Searching…
            </p>
          )}
          {!isFetching && all.length === 0 && (
            <p style={{ ...rowMutedStyle, padding: "0.6rem 0.85rem" }}>
              No matches.
            </p>
          )}
          {matches.length > 0 && (
            <SectionHeader>Matches</SectionHeader>
          )}
          {matches.map((row, i) => (
            <Row
              key={`m-${row.id}`}
              row={row}
              active={activeIdx === i}
              onMouseEnter={() => setActiveIdx(i)}
              onClick={() => pick(row)}
            />
          ))}
          {suggestions.length > 0 && (
            <SectionHeader>Suggestions</SectionHeader>
          )}
          {suggestions.map((row, j) => {
            const i = matches.length + j;
            return (
              <Row
                key={`s-${row.id}`}
                row={row}
                active={activeIdx === i}
                onMouseEnter={() => setActiveIdx(i)}
                onClick={() => pick(row)}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}

function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <p
      style={{
        margin: 0,
        padding: "0.4rem 0.85rem",
        fontSize: fontSize.xs,
        textTransform: "uppercase",
        letterSpacing: "0.08em",
        color: "var(--db-text-muted, #a3a3a3)",
        background: "var(--db-surface, #0a0a0a)",
        borderBottom: "1px solid var(--db-border-subtle, #1f1f1f)",
      }}
    >
      {children}
    </p>
  );
}

function Row({
  row, active, onMouseEnter, onClick,
}: {
  row: CustomerRow;
  active: boolean;
  onMouseEnter: () => void;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onMouseEnter={onMouseEnter}
      onClick={onClick}
      style={{
        display: "block",
        width: "100%",
        textAlign: "left",
        padding: "0.55rem 0.85rem",
        background: active
          ? "var(--db-surface, #0a0a0a)"
          : "transparent",
        color: "var(--db-text, #f5f5f5)",
        border: "none",
        borderBottom: "1px solid var(--db-border-subtle, #1f1f1f)",
        cursor: "pointer",
      }}
    >
      <div style={{ fontWeight: 500 }}>{row.full_name}</div>
      <div style={rowMutedStyle}>
        <span
          style={{
            fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
          }}
        >
          {row.phone_country} {row.phone_number || "—"}
        </span>
        {row.home_store_name && (
          <span style={{ marginLeft: "0.5rem" }}>
            · from {row.home_store_name}
          </span>
        )}
      </div>
    </button>
  );
}

const inputStyle: React.CSSProperties = {
  background: "var(--db-surface, #0a0a0a)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.5rem",
  padding: "0.55rem 0.75rem",
  color: "var(--db-text, #f5f5f5)",
  fontFamily: "var(--db-font-body, 'Inter', system-ui, sans-serif)",
  fontSize: fontSize.base,
  outline: "none",
  width: "100%",
  boxSizing: "border-box",
};

const popoverStyle: React.CSSProperties = {
  position: "absolute",
  top: "calc(100% + 4px)",
  left: 0,
  right: 0,
  background: "var(--db-surface-2, #141414)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.5rem",
  boxShadow: "0 6px 24px rgba(0, 0, 0, 0.5)",
  zIndex: 10,
  maxHeight: "20rem",
  overflowY: "auto",
};

const rowMutedStyle: React.CSSProperties = {
  fontSize: "0.85rem",
  color: "var(--db-text-muted, #a3a3a3)",
  margin: 0,
};
