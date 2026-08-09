// ================== DOCODIVE SERVICE WORKER ==================
const CACHE_VERSION = 'v1.0.1';
const STATIC_CACHE = `docodive-static-${CACHE_VERSION}`;
const IMAGE_CACHE = `docodive-images-${CACHE_VERSION}`;

// Assets to precache on install
const PRECACHE_URLS = [
  '/',
  '/static/css/style.css',
  '/static/js/main.js',
  '/static/images/docodive-og.jpg',
  '/static/default-avatar.png',
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

// ================== ACTIVATE ==================
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
    }).then(() => self.clients.claim())
  );
});

// ================== FETCH ==================
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET requests
  if (request.method !== 'GET') return;

  // Skip third-party analytics and chat
  if (url.hostname.includes('brevo.com') ||
      url.hostname.includes('conversations-widget') ||
      url.hostname.includes('googletagmanager.com') ||
      url.hostname.includes('google-analytics.com')) return;

  // Skip social login callbacks
  if (url.pathname.startsWith('/auth/') || url.pathname.startsWith('/login/')) return;

  // Cache-first for static assets
  if (request.url.match(/\.(css|js|png|jpg|jpeg|gif|svg|ico|woff2?|ttf|eot)(\?.*)?$/)) {
    event.respondWith(
      caches.match(request).then(cached => cached || fetch(request).then(response => {
        if (response.ok) {
          const clone = response.clone();
          const cacheName = url.pathname.includes('/images/') || url.pathname.includes('/covers/') ?
            IMAGE_CACHE : STATIC_CACHE;
          caches.open(cacheName).then(cache => cache.put(request, clone));
        }
        return response;
      }))
    );
    return;
  }

  // Network-first for HTML pages
  if (request.headers.get('Accept')?.includes('text/html')) {
    event.respondWith(
      fetch(request).then(response => {
        if (response.ok) {
          const clone = response.clone();
          caches.open(STATIC_CACHE).then(cache => cache.put(request, clone));
        }
        return response;
      }).catch(() => caches.match(request))
    );
    return;
  }

  // Stale-while-revalidate for other requests
  event.respondWith(
    caches.match(request).then(cached => {
      const fetchPromise = fetch(request).then(response => {
        if (response.ok) {
          const clone = response.clone();
          caches.open(STATIC_CACHE).then(cache => cache.put(request, clone));
        }
        return response;
      });
      return cached || fetchPromise;
    })
  );
});

// ================== MESSAGE HANDLER ==================
self.addEventListener('message', event => {
  if (event.data === 'CLEAR_CACHES') {
    caches.keys().then(names => Promise.all(names.map(n => caches.delete(n))));
  }
});
