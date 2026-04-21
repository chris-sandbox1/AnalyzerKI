// FloorballIQ Service Worker
// Strategie: Cache-first für App-Shell (HTML + Icons), Network-first für API

const CACHE_NAME = 'floorballiq-v3';

// Dateien die beim Installieren sofort gecacht werden
const PRECACHE_URLS = [
  '/AnalyzerKI/saisonmanager.html',
  '/AnalyzerKI/icons/icon-192.png',
  '/AnalyzerKI/icons/icon-512.png',
  '/AnalyzerKI/manifest.json',
];

// ── Install: App-Shell voraufladen ────────────────────────────────────────────
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(PRECACHE_URLS))
  );
  // Sofort aktiv werden, ohne auf alten SW zu warten
  self.skipWaiting();
});

// ── Activate: Alte Caches aufräumen ──────────────────────────────────────────
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

// ── Fetch: Cache-first für App-Shell, Network für API ────────────────────────
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // API-Anfragen zu saisonmanager.de immer live abrufen
  if (url.hostname === 'saisonmanager.de') {
    event.respondWith(fetch(event.request));
    return;
  }

  // App-Shell: Cache-first (bei Fehler trotzdem Netz versuchen)
  event.respondWith(
    caches.match(event.request).then(cached => {
      if (cached) return cached;
      return fetch(event.request).then(response => {
        // Erfolgreiche Antworten für App-eigene Dateien nachträglich cachen
        if (response.ok && url.origin === self.location.origin) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
        }
        return response;
      });
    })
  );
});
