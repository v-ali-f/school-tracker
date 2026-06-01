const CACHE_NAME = 'school-portal-pwa-v1';

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
