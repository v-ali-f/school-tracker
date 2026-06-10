const CACHE_NAME = 'altair-portal-pwa-v2';

self.addEventListener('install', event => {
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', event => {
  // Портал всегда берём с сервера, чтобы обновления подтягивались сразу.
  return;
});
