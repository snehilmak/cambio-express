import { useEffect } from "react";

// Warn the user before they lose unsaved edits.
//
// While `dirty` is true this arms a `beforeunload` handler, so the
// browser shows its native "Leave site? Changes you made may not be
// saved." dialog on tab close, refresh, or navigating to an external
// URL. Pair it in the component with:
//   • a visible "unsaved changes" indicator, and
//   • a confirm on the page's own Cancel / back control.
//
// Note on scope: this app uses react-router's declarative
// <BrowserRouter>, where `useBlocker` isn't available (it requires a
// data router), so in-app SPA navigations — e.g. clicking a sidebar
// link mid-edit — are NOT intercepted here. Closing that gap would
// mean migrating to a data router; until then, guard the explicit
// leave actions in the component and rely on `beforeunload` for hard
// navigations.
export function useUnsavedChangesGuard(dirty: boolean): void {
  useEffect(() => {
    if (!dirty) return;
    function onBeforeUnload(e: BeforeUnloadEvent) {
      // Both are needed across browsers to trigger the native prompt.
      e.preventDefault();
      e.returnValue = "";
    }
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirty]);
}
