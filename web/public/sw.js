/* Nightsquad service worker: caches the app shell and shows alerts. It never caches API answers. */
const CACHE = "nightsquad-shell-v1";
const SHELL = ["/", "/manifest.webmanifest", "/icon.svg", "/icon-192.png"];
const NEVER_CACHED = ["/v1/", "/files/", "/stream/", "/healthz", "/readyz", "/gateway/", "/agent/", "/mcp/"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(SHELL))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin) return;
  if (NEVER_CACHED.some((prefix) => url.pathname.startsWith(prefix))) return;

  if (request.mode === "navigate") {
    // Pages: the network first, the cached shell when offline.
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) {
            const copy = response.clone();
            event.waitUntil(caches.open(CACHE).then((cache) => cache.put("/", copy)));
          }
          return response;
        })
        .catch(() => caches.match("/").then((cached) => cached || Response.error())),
    );
    return;
  }

  // Built files have hashed names: serve from the cache, and fill it from the network.
  event.respondWith(
    caches.match(request).then(
      (cached) =>
        cached ||
        fetch(request).then((response) => {
          if (response.ok && response.type === "basic") {
            const copy = response.clone();
            event.waitUntil(caches.open(CACHE).then((cache) => cache.put(request, copy)));
          }
          return response;
        }),
    ),
  );
});

self.addEventListener("push", (event) => {
  let payload = {};
  try {
    payload = event.data ? event.data.json() : {};
  } catch (error) {
    payload = { body: event.data ? event.data.text() : "" };
  }
  const title = typeof payload.title === "string" && payload.title ? payload.title : "nightsquad";
  event.waitUntil(
    self.registration.showNotification(title, {
      body: typeof payload.body === "string" ? payload.body : "",
      icon: "/icon-192.png",
      badge: "/icon-192.png",
      data: { project_id: typeof payload.project_id === "string" ? payload.project_id : null },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const projectId = event.notification.data && event.notification.data.project_id;
  const path = projectId ? "/projects/" + encodeURIComponent(projectId) : "/";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
      for (const client of windows) {
        if ("navigate" in client && "focus" in client) {
          return client.navigate(path).then((opened) => (opened || client).focus());
        }
      }
      return self.clients.openWindow(path);
    }),
  );
});
