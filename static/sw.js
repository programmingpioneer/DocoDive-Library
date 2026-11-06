(() => {
// ================== DOCODIVE SERVICE WORKER (FIXED) ==================
const CACHE_VERSION = 'v1.0.22';
const STATIC_CACHE = `docodive-static-${CACHE_VERSION}`;
const IMAGE_CACHE = `docodive-images-${CACHE_VERSION}`;
// DEV: Service worker temporarily disabled
if (self.location.hostname === 'localhost' || self.location.hostname === '127.0.0.1' || self.location.hostname.startsWith('192.168.')) {
  self.addEventListener('install', event => self.skipWaiting());
  self.addEventListener('activate', event => self.registration.unregister());
  return;
}

// Assets to precache on install — '/' REMOVED (HTML should never be cached)
const PRECACHE_URLS = [
  // '/'  ← REMOVED — dynamic HTML, session-dependent
  '/static/css/style.css',
  '/static/js/main.js',
  '/static/images/docoDive-og.jpg',
  '/static/images/default-avatar.jpg',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css',
  'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.1/font/bootstrap-icons.css',
  'https://unpkg.com/aos@2.3.1/dist/aos.css',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js',
  'https://unpkg.com/aos@2.3.1/dist/aos.js'
];

// ================== INSTALL ==================
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then(cache => {
        console.log('SW: Pre-caching static assets');
        return Promise.allSettled(
          PRECACHE_URLS.map(url =>
            cache.add(url).catch(err => console.warn(`SW: Failed to cache ${url}`, err))
          )
        );
      })
      .then(() => self.skipWaiting())
  );
});

// ================== ACTIVATE (Force Update) ==================
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.filter(name => {
          return (name.startsWith('docodive-') &&
            name !== STATIC_CACHE &&
            name !== IMAGE_CACHE);
        }).map(name => {
          console.log('SW: Deleting old cache', name);
          return caches.delete(name);
        })
      );
    }).then(() => {
      // Force all clients to refresh
      return self.clients.matchAll().then(clients => {
        clients.forEach(client => {
          client.postMessage({ action: 'refresh' });
        });
      });
    }).then(() => self.clients.claim())
  );
});

// ================== FETCH ==================
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET requests
  if (request.method !== 'GET') return;

  // Only explicitly public, same-origin static assets may enter this cache.
  // All HTML, account, Studio and API requests go directly to the network.
  if (url.origin !== self.location.origin || !url.pathname.startsWith('/static/')) return;
  event.respondWith(caches.match(request).then(cached => cached || fetch(request).then(response => {
    const policy = response.headers.get('Cache-Control') || '';
    if (response.ok && !response.redirected && !/no-store|private/i.test(policy)) {
      const copy = response.clone();
      event.waitUntil(caches.open(STATIC_CACHE).then(cache => cache.put(request, copy)));
    }
    return response;
  })));
});

// ================== MESSAGE HANDLER ==================
self.addEventListener('message', event => {
  if (event.data === 'CLEAR_CACHES') {
    caches.keys().then(names => Promise.all(names.map(n => caches.delete(n))));
  }
});
})();
