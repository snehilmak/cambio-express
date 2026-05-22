import { Link } from "react-router-dom";

import { Tooltip } from "./ui";
import styles from "./HomeButton.module.css";

/** Topbar shortcut to /app/home — always one tap away from
 *  the tile-hub, regardless of where the user is in the SPA. */
export function HomeButton() {
  return (
    <Tooltip label="Open the home hub — every action, one tap away">
    <Link
      to="/home"
      className={styles.button}
      aria-label="Home"
    >
      <svg
        width="16" height="16" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" strokeWidth="2"
        strokeLinecap="round" strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M3 12l9-9 9 9" />
        <path d="M5 10v10a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V10" />
      </svg>
      <span className={styles.label}>Home</span>
    </Link>
    </Tooltip>
  );
}
