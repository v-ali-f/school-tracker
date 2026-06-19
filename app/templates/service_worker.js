const CACHE_NAME = "altair-portal-pwa-v4";
const APP_URL = "/";
const DEFAULT_ICON = "/static/brand/altair/altair-app-icon-512.png";
const DEFAULT_BADGE = "/static/brand/altair/altair-app-icon-128.png";
const FIREBASE_CONFIG = {{ pwa_firebase_config | tojson }};
const FIREBASE_READY = {{ pwa_firebase_ready | tojson }};

async function syncBadge(rawCount) {
  const unreadCount = Math.max(Number(rawCount) || 0, 0);
  try {
    if (unreadCount > 0 && self.navigator && typeof self.navigator.setAppBadge === "function") {
      await self.navigator.setAppBadge(unreadCount);
    } else if (unreadCount <= 0 && self.navigator && typeof self.navigator.clearAppBadge === "function") {
      await self.navigator.clearAppBadge();
    }
  } catch (_) {}

  const clientsList = await self.clients.matchAll({type: "window", includeUncontrolled: true});
  for (const client of clientsList) {
    client.postMessage({
      type: "ALTair_PWA_BADGE_SYNC",
      unreadCount: unreadCount,
    });
  }
}

function notificationLink(data) {
  if (!data) return APP_URL;
  return data.link || APP_URL;
}

self.addEventListener("install", (event) => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", (event) => {
  return;
});

self.addEventListener("message", (event) => {
  const data = event && event.data ? event.data : {};
  if (data.type === "SET_BADGE") {
    event.waitUntil(syncBadge(data.unreadCount));
  } else if (data.type === "REFRESH_BADGE") {
    event.waitUntil((async () => {
      const clientsList = await self.clients.matchAll({type: "window", includeUncontrolled: true});
      for (const client of clientsList) {
        client.postMessage({type: "ALTair_PWA_REFRESH_BADGE"});
      }
    })());
  }
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const data = event.notification && event.notification.data ? event.notification.data : {};
  const url = notificationLink(data);
  event.waitUntil((async () => {
    const allClients = await self.clients.matchAll({type: "window", includeUncontrolled: true});
    for (const client of allClients) {
      if ("focus" in client) {
        client.postMessage({type: "ALTair_PWA_REFRESH_BADGE"});
        try {
          await client.focus();
          if ("navigate" in client && url) {
            await client.navigate(url);
          }
          return;
        } catch (_) {}
      }
    }
    if (self.clients.openWindow) {
      await self.clients.openWindow(url || APP_URL);
    }
  })());
});

if (FIREBASE_READY) {
  importScripts("https://www.gstatic.com/firebasejs/11.0.1/firebase-app-compat.js");
  importScripts("https://www.gstatic.com/firebasejs/11.0.1/firebase-messaging-compat.js");

  firebase.initializeApp(FIREBASE_CONFIG);
  const messaging = firebase.messaging();

  messaging.onBackgroundMessage((payload) => {
    const data = payload && payload.data ? payload.data : {};
    const notification = payload && payload.notification ? payload.notification : {};
    const unreadCount = data.unread_count || data.badge_count || 0;
    const title = notification.title || data.title || "Новое уведомление";
    const body = notification.body || data.body || "";
    const options = {
      body: body,
      icon: notification.icon || DEFAULT_ICON,
      badge: notification.badge || DEFAULT_BADGE,
      data: {
        link: notificationLink(data),
      },
    };

    self.registration.showNotification(title, options);
    syncBadge(unreadCount);
  });
}
