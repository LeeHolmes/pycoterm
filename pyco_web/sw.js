// Service Worker for pyco PWA
const CACHE_NAME = 'pyco-v2';
const ASSETS_TO_CACHE = [
  './',
  './index.html',
  './pyrepl.js',
  './pyrepl.esm.js',
  './chunk-1qs0a4h5.js',
  './chunk-az66snk4.js',
  './chunk-dtbj3q3c.js',
  './chunk-p8z2rk6s.js',
  './chunk-q8xkh3ym.js',
  './chunk-zvesc6aa.js',
  './pyco.ico',
  './icons/icon-192.png',
  './icons/icon-512.png',
  './manifest.json'
];

// Install event - cache core assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ASSETS_TO_CACHE);
    })
  );
  // Activate immediately
  self.skipWaiting();
});

// Activate event - clean up old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name !== CACHE_NAME)
          .map((name) => caches.delete(name))
      );
    })
  );
  // Take control immediately
  self.clients.claim();
});

// Fetch event - cache first for local assets, network first for external
self.addEventListener('fetch', (event) => {
  // Skip non-GET requests
  if (event.request.method !== 'GET') return;
  
  const isLocalAsset = event.request.url.startsWith(self.location.origin);
  const isPyodide = event.request.url.includes('cdn.jsdelivr.net/pyodide') || 
                    event.request.url.includes('pyodide');

  if (isLocalAsset) {
    // Cache first for local assets (faster offline experience)
    event.respondWith(
      caches.match(event.request).then((cachedResponse) => {
        if (cachedResponse) {
          return cachedResponse;
        }
        return fetch(event.request).then((response) => {
          if (response.status === 200) {
            const responseClone = response.clone();
            caches.open(CACHE_NAME).then((cache) => {
              cache.put(event.request, responseClone);
            });
          }
          return response;
        });
      })
    );
  } else if (isPyodide) {
    // Cache Pyodide resources for offline use
    event.respondWith(
      caches.match(event.request).then((cachedResponse) => {
        if (cachedResponse) {
          return cachedResponse;
        }
        return fetch(event.request).then((response) => {
          if (response.status === 200) {
            const responseClone = response.clone();
            caches.open(CACHE_NAME).then((cache) => {
              cache.put(event.request, responseClone);
            });
          }
          return response;
        });
      })
    );
  } else {
    // Network first for other external resources
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          if (response.status === 200) {
            const responseClone = response.clone();
            caches.open(CACHE_NAME).then((cache) => {
              cache.put(event.request, responseClone);
            });
          }
          return response;
        })
        .catch(() => {
          return caches.match(event.request);
        })
    );
  }
});
