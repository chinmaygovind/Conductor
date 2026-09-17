// Conductor — Service Worker
// Enables PWA "Add to Home Screen". Uses network-first for all content so
// Flask's ?v= cache-busting keeps working normally; cache is fallback only.

const CACHE = 'conductor-v1';

self.addEventListener('install', e => {
  // Pre-cache the icon so it loads on the home screen even without network
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(['/static/images/icon.svg'])).catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const { request } = e;
  const url = new URL(request.url);

  // Skip non-GET, socket.io, and server-side routes
  if (request.method !== 'GET') return;
  if (url.pathname.startsWith('/socket.io')) return;
  if (url.pathname.startsWith('/api/')) return;
  if (url.pathname.startsWith('/auth/')) return;

  // Static assets: network-first, fall back to cache when offline
  if (url.pathname.startsWith('/static/')) {
    e.respondWith(
      fetch(request)
        .then(res => {
          if (res.ok) {
            const clone = res.clone();
            caches.open(CACHE).then(c => c.put(request, clone));
          }
          return res;
        })
        .catch(() => caches.match(request))
    );
  }
  // All other requests (HTML pages, login, lobbies, game) — straight to network
});
