// Theme helpers — applies dark/light to the document, caches the
// choice in localStorage, and reconciles with the server-side
// User.theme_preference on first profile fetch.
//
// Two layers of persistence:
//   1. Per-device cache (``localStorage``) — restored by the inline
//      script in index.html before first paint so reloads don't
//      flash. Also keeps logged-out pages on the right theme.
//   2. Per-user setting (``User.theme_preference`` via PUT
//      /api/v2/auth/profile) — follows the user across browsers
//      and devices.
//
// The two converge in ``reconcileTheme()``: when we load a fresh
// profile payload, we apply the server's preference (it wins) AND
// rewrite the local cache so the next reload uses it.

export type Theme = "dark" | "light";

const STORAGE_KEY = "dinerobook.theme";

function isTheme(v: string | null): v is Theme {
  return v === "dark" || v === "light";
}

export function getCurrentTheme(): Theme {
  const attr = document.documentElement.getAttribute("data-theme");
  return isTheme(attr) ? attr : "dark";
}

export function applyTheme(theme: Theme): void {
  document.documentElement.setAttribute("data-theme", theme);
  try {
    window.localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    /* localStorage blocked / quota — toggle still works for the
       current page, it just won't survive a reload. */
  }
}

// Called after a profile fetch lands. If the server says something
// different from what we have on the device, the server wins —
// that matches the "preference follows the user across devices"
// model. Logged-out / pre-fetch state stays on the local cache.
export function reconcileTheme(serverPreference: Theme | undefined): void {
  if (!serverPreference) return;
  if (getCurrentTheme() !== serverPreference) {
    applyTheme(serverPreference);
  }
}
