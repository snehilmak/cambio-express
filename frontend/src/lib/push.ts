// Web Push subscription helpers.
//
// The SPA flow:
//   1. ``pushSupported()`` gates the UI — Safari pre-16.4, older
//      Firefox, etc. don't expose the PushManager API.
//   2. ``getPushPermission()`` reads ``Notification.permission``
//      so the UI shows the right CTA (default / granted / denied).
//   3. ``subscribeBrowser()`` runs the actual subscription flow:
//      register the service worker, call PushManager.subscribe()
//      with the server's VAPID public key, then POST the
//      envelope to ``/api/v2/auth/push/subscribe``.
//   4. ``unsubscribeBrowser()`` unsubscribes locally + tells the
//      server to drop the row.
//
// The service worker lives at ``/sw.js`` (registered separately —
// see ``Landing.tsx`` / the existing PWA install flow).  We
// re-register it here defensively to handle the case where the
// user lands directly on an authed route and never hit Landing.

export type PushPermission = "default" | "granted" | "denied";


/** Does this browser support the Web Push + Notifications APIs?
 *  False on iOS Safari < 16.4 / older Firefox / embedded webviews
 *  — the UI hides the section entirely in that case. */
export function pushSupported(): boolean {
  if (typeof window === "undefined") return false;
  return (
    "serviceWorker" in navigator
    && "PushManager" in window
    && "Notification" in window
  );
}


/** Current notification permission for this origin.  Returns
 *  ``"default"`` if the prompt hasn't fired yet, ``"granted"``
 *  once the user allows, ``"denied"`` once the user blocks (a
 *  blocked origin can't re-prompt — the user has to clear it
 *  from browser settings). */
export function getPushPermission(): PushPermission {
  if (!pushSupported()) return "denied";
  return Notification.permission as PushPermission;
}


/** Subscribe this browser to push.  Resolves with the envelope
 *  ready to POST to ``/api/v2/auth/push/subscribe``; the caller
 *  is responsible for the API call so it can update React Query
 *  cache accordingly. */
export async function subscribeBrowser(
  vapidPublicKey: string,
): Promise<{ endpoint: string; p256dh: string; auth: string; userAgent: string }> {
  if (!pushSupported()) {
    throw new Error("This browser doesn't support push notifications.");
  }
  if (Notification.permission === "denied") {
    throw new Error(
      "Notifications are blocked. Allow notifications for this site in "
      + "your browser settings, then try again.",
    );
  }
  // Request permission if the user hasn't decided yet.  ``default``
  // → prompts; ``granted`` → no-op; ``denied`` already caught above.
  if (Notification.permission === "default") {
    const result = await Notification.requestPermission();
    if (result !== "granted") {
      throw new Error("Notifications permission denied.");
    }
  }

  // Make sure the service worker is registered.  Idempotent — if
  // another flow (PWA install, etc.) registered it earlier the
  // returned registration is the same object.
  const reg = await navigator.serviceWorker.register("/sw.js");
  await navigator.serviceWorker.ready;

  // PushManager wants the application server key as a BufferSource.
  // The stricter TS lib types reject ``Uint8Array<ArrayBufferLike>``
  // because its underlying buffer could (in theory) be a
  // SharedArrayBuffer; at runtime we always allocate a plain
  // ArrayBuffer, so coerce via ``buffer.slice()`` to a fresh one.
  const raw = urlBase64ToUint8Array(vapidPublicKey);
  const fresh = new Uint8Array(raw.byteLength);
  fresh.set(raw);
  const sub = await reg.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: fresh,
  });

  return envelope(sub);
}


/** Drop the local push subscription.  Returns the endpoint that
 *  was unsubscribed, or empty string if there wasn't one — the
 *  caller passes that to the server DELETE. */
export async function unsubscribeBrowser(): Promise<string> {
  if (!pushSupported()) return "";
  const reg = await navigator.serviceWorker.getRegistration();
  if (!reg) return "";
  const sub = await reg.pushManager.getSubscription();
  if (!sub) return "";
  const endpoint = sub.endpoint;
  await sub.unsubscribe();
  return endpoint;
}


/** Whether this browser already has an active push subscription
 *  — drives the "Enabled on this device" badge. */
export async function hasLocalSubscription(): Promise<boolean> {
  if (!pushSupported()) return false;
  const reg = await navigator.serviceWorker.getRegistration();
  if (!reg) return false;
  const sub = await reg.pushManager.getSubscription();
  return sub !== null;
}


// ── Internal helpers ──────────────────────────────────────


function envelope(sub: PushSubscription): {
  endpoint: string; p256dh: string; auth: string; userAgent: string;
} {
  const p256dh = arrayBufferToBase64(sub.getKey("p256dh"));
  const auth   = arrayBufferToBase64(sub.getKey("auth"));
  return {
    endpoint: sub.endpoint,
    p256dh,
    auth,
    userAgent: navigator.userAgent.slice(0, 255),
  };
}


function urlBase64ToUint8Array(b64: string): Uint8Array {
  // VAPID keys arrive in URL-safe base64 (no ``=`` padding,
  // ``-`` instead of ``+``, ``_`` instead of ``/``).  PushManager
  // wants a Uint8Array of the raw bytes.
  const padding = "=".repeat((4 - (b64.length % 4)) % 4);
  const standard = (b64 + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = window.atob(standard);
  const arr = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i);
  return arr;
}


function arrayBufferToBase64(buf: ArrayBuffer | null): string {
  if (!buf) return "";
  const bytes = new Uint8Array(buf);
  let str = "";
  for (let i = 0; i < bytes.length; i++) str += String.fromCharCode(bytes[i]);
  return window.btoa(str);
}
