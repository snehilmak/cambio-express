// DineroBook service worker
// Minimal: caches the app shell assets so install works and iconography
// renders quickly. Everything else is network-first — this is a live
// financial dashboard, not a content site, so we never want stale data.
const CACHE = 'dinerobook-v1';
const SHELL = [
  '/static/app.css',
  '/static/logo.svg',
  '/static/logo-200.png',
  '/static/manifest.webmanifest'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL)).catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // Cache-first for the static shell — fonts, CSS, icons.
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(req).then((hit) =>
        hit || fetch(req).then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy));
          return res;
        }).catch(() => hit)
      )
    );
    return;
  }
  // Everything else: straight network. No caching of dashboard data.
});
