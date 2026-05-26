import { useEffect, useRef, useState } from "react";
import { DayPicker } from "react-day-picker";
import "react-day-picker/style.css";

import { Input } from "./Input";
import styles from "./DateInput.module.css";

/**
 * Date input with a calendar popover. Drop-in replacement for
 * `<Input type="date" />` — same value format (YYYY-MM-DD string),
 * same onChange signature, but with a consistent cross-browser
 * calendar picker styled for the design system.
 *
 * Falls back to the raw input value for manual typing.
 */
export function DateInput({
  value,
  onChange,
  required,
  disabled,
  placeholder = "YYYY-MM-DD",
  ...rest
}: {
  value: string;
  onChange: (e: { target: { value: string } }) => void;
  required?: boolean;
  disabled?: boolean;
  placeholder?: string;
  className?: string;
  style?: React.CSSProperties;
  "aria-label"?: string;
}) {
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);

  const selected = value ? new Date(value + "T00:00:00") : undefined;

  function handleSelect(day: Date | undefined) {
    if (!day) return;
    const iso = [
      day.getFullYear(),
      String(day.getMonth() + 1).padStart(2, "0"),
      String(day.getDate()).padStart(2, "0"),
    ].join("-");
    onChange({ target: { value: iso } });
    setOpen(false);
  }

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <div className={styles.wrapper} ref={wrapperRef}>
      <Input
        type="text"
        value={value}
        onChange={onChange}
        onFocus={() => !disabled && setOpen(true)}
        onClick={() => !disabled && setOpen(true)}
        placeholder={placeholder}
        required={required}
        disabled={disabled}
        readOnly={false}
        className={`${styles.trigger} ${rest.className ?? ""}`}
        style={rest.style}
        aria-label={rest["aria-label"]}
      />
      {open && (
        <>
          <div className={styles.backdrop} onClick={() => setOpen(false)} />
          <div className={styles.popover}>
            <DayPicker
              mode="single"
              selected={selected}
              onSelect={handleSelect}
              defaultMonth={selected}
            />
          </div>
        </>
      )}
    </div>
  );
}
