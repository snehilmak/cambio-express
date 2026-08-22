import { Tooltip } from "./ui";
import { useInstallPrompt } from "../lib/installPrompt";
import styles from "./InstallAppButton.module.css";
import { BRAND_NAME } from "../lib/brand";

/** Topbar button that triggers the browser's PWA install
 *  prompt. Self-hides when the install isn't available
 *  (already installed, browser doesn't support
 *  ``beforeinstallprompt``, user dismissed and the browser
 *  hasn't re-armed the event). */
export function InstallAppButton() {
  const { canInstall, promptInstall } = useInstallPrompt();
  if (!canInstall) return null;
  return (
    <Tooltip label={`Install ${BRAND_NAME} as a standalone app on this device`}>
    <button
      type="button"
      className={styles.button}
      onClick={() => { void promptInstall(); }}
      aria-label={`Install ${BRAND_NAME} as an app`}
    >
      <svg
        width="16" height="16" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" strokeWidth="2"
        strokeLinecap="round" strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
        <polyline points="7 10 12 15 17 10" />
        <line x1="12" y1="15" x2="12" y2="3" />
      </svg>
      <span className={styles.label}>Install app</span>
    </button>
    </Tooltip>
  );
}
