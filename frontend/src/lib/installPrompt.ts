// Cross-browser PWA install-prompt helper.
//
// Most desktop / Android browsers (Chrome, Edge, Brave, Samsung
// Internet, Opera) fire a ``beforeinstallprompt`` event when the
// site meets installability criteria + the user hasn't already
// installed it. We capture the event, surface an "Install app"
// button in the topbar, and call ``prompt()`` on the saved
// event when the button is clicked.
//
// iOS Safari + macOS Safari don't fire the event — install
// happens via the OS-level Share menu instead. We detect
// "running in standalone" via ``matchMedia('(display-mode:
// standalone)')`` so the button hides once the app is launched
// from the home screen / dock regardless of how it got there.
//
// Service-worker registration also lives here so PWA setup is
// one import. Logged-out pages already register ``/sw.js`` via
// their own Jinja templates; this duplicate call is idempotent
// — the browser dedups by scope.

import { useEffect, useState } from "react";

interface BeforeInstallPromptEvent extends Event {
  readonly platforms: string[];
  prompt(): Promise<void>;
  readonly userChoice: Promise<{
    outcome: "accepted" | "dismissed";
    platform: string;
  }>;
}


/** Register the service worker once per session. Safe to call
 *  from anywhere — the browser dedups by scope, and we swallow
 *  errors (file:// previews, private windows on some browsers,
 *  CSP-restricted environments). */
export function registerServiceWorker(): void {
  if (typeof window === "undefined") return;
  if (!("serviceWorker" in navigator)) return;
  try {
    void navigator.serviceWorker.register("/sw.js");
  } catch {
    /* private mode / file:// / CSP — silent failure is fine,
       the PWA features just won't activate. */
  }
}


/** Returns ``true`` when the app is currently running in a
 *  PWA / standalone context (installed + launched from the
 *  home screen / dock, or running fullscreen). Hides the
 *  Install button when true. */
function _isStandalone(): boolean {
  if (typeof window === "undefined") return false;
  if (window.matchMedia("(display-mode: standalone)").matches) return true;
  if (window.matchMedia("(display-mode: fullscreen)").matches) return true;
  // iOS Safari sets this non-standard property when running
  // from the home screen.
  const navAny = window.navigator as Navigator & { standalone?: boolean };
  return Boolean(navAny.standalone);
}


/** React hook that exposes the install state + the prompt
 *  trigger. Drop the returned ``InstallButton`` in any chrome
 *  surface; it self-hides when the install isn't available
 *  (already installed, browser doesn't support, user dismissed
 *  recently). */
export function useInstallPrompt() {
  const [evt, setEvt] = useState<BeforeInstallPromptEvent | null>(null);
  const [installed, setInstalled] = useState<boolean>(_isStandalone);

  useEffect(() => {
    function onBeforeInstall(e: Event) {
      // Stop the browser's own install banner so we can show
      // our chrome button instead.
      e.preventDefault();
      setEvt(e as BeforeInstallPromptEvent);
    }
    function onAppInstalled() {
      setEvt(null);
      setInstalled(true);
    }
    window.addEventListener("beforeinstallprompt", onBeforeInstall);
    window.addEventListener("appinstalled", onAppInstalled);
    // Listen for display-mode changes (browser → standalone
    // transition without a reload, rare but possible).
    const mq = window.matchMedia("(display-mode: standalone)");
    const onDmChange = (e: MediaQueryListEvent) => setInstalled(e.matches);
    if (mq.addEventListener) {
      mq.addEventListener("change", onDmChange);
    }
    return () => {
      window.removeEventListener("beforeinstallprompt", onBeforeInstall);
      window.removeEventListener("appinstalled", onAppInstalled);
      if (mq.removeEventListener) {
        mq.removeEventListener("change", onDmChange);
      }
    };
  }, []);

  /** True when our chrome should show an Install button. */
  const canInstall = Boolean(evt) && !installed;

  async function promptInstall(): Promise<"accepted" | "dismissed" | "unavailable"> {
    if (!evt) return "unavailable";
    await evt.prompt();
    const choice = await evt.userChoice;
    if (choice.outcome === "accepted") {
      setEvt(null);
      setInstalled(true);
    } else {
      // Saved event can only be used once — clear it so the
      // button reflects the dismissal until the browser fires
      // ``beforeinstallprompt`` again.
      setEvt(null);
    }
    return choice.outcome;
  }

  return { canInstall, installed, promptInstall };
}
