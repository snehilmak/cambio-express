// DineroBook service worker
// - Cache-first for the /static/ shell (CSS, icons)
// - Network-first for navigations with /offline as fallback
// - Push notifications (show + handle click)
const CACHE = 'dinerobook-v4';
const SHELL = [
  '/offline',
  '/static/app.css',
  '/static/design-tokens.css',
  '/static/shell.css',
  '/static/logo.svg',
  '/static/logo-192.png',
  '/static/logo-512.png',
  '/static/manifest.webmanifest'
];
// Stylesheets that should go network-first so deploys roll out
// without waiting for a cache bust.
const NETWORK_FIRST_CSS = new Set([
  '/static/app.css',
  '/static/design-tokens.css',
  '/static/shell.css',
]);

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL)).catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // Navigations: network first, offline page on failure.
  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req).catch(() => caches.match('/offline'))
    );
    return;
  }

  // Stylesheets: network first so CSS updates roll out immediately.
  // CSS is small and updated often — cache-first here has bitten users
  // who kept seeing stale layouts after deploys.
  if (NETWORK_FIRST_CSS.has(url.pathname)) {
    event.respondWith(
      fetch(req).then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(req, copy));
        return res;
      }).catch(() => caches.match(req))
    );
    return;
  }

  // Other static shell assets: cache first, populate on miss.
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
  // API / data: straight network. Never cached.
});

// ── Push notifications ───────────────────────────────────────
self.addEventListener('push', (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (e) { data = { title: 'DineroBook', body: event.data ? event.data.text() : '' }; }
  const title = data.title || 'DineroBook';
  const opts = {
    body: data.body || '',
    icon: '/static/logo-192.png',
    badge: '/static/logo-192.png',
    data: { url: data.url || '/' },
    tag: data.tag || undefined
  };
  event.waitUntil(self.registration.showNotification(title, opts));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || '/';
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((list) => {
      for (const c of list) {
        if (c.url.endsWith(url) && 'focus' in c) return c.focus();
      }
      if (clients.openWindow) return clients.openWindow(url);
    })
  );
});
