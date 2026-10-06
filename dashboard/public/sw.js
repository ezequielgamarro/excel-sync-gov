/*
 * Service Worker de SOLO SHELL (T47, RNF-10.e, AM-10).
 *
 * Reglas inviolables:
 *  - Precachea únicamente el app shell (HTML, manifest y assets estáticos
 *    same-origin con hash). NUNCA cachea respuestas de API ni tramas WSS.
 *  - Cualquier request a `/api/`, `/ws`, esquemas `ws:`/`wss:`, o con métodos
 *    distintos de GET/HEAD, se ignora por completo (va directo a la red).
 *  - Los datos deben seguir `no-store`; el SW no los almacena jamás.
 */

const SHELL_CACHE = "dash-shell-v1";
const APP_SHELL = ["./", "./index.html", "./manifest.webmanifest", "./icons/icon.svg"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(SHELL_CACHE)
      .then((cache) => cache.addAll(APP_SHELL))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== SHELL_CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

function isApiOrRealtime(url, request) {
  if (url.protocol === "ws:" || url.protocol === "wss:") return true;
  if (url.pathname.startsWith("/api/")) return true;
  if (url.pathname.startsWith("/ws")) return true;
  if (request.method !== "GET" && request.method !== "HEAD") return true;
  return false;
}

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (isApiOrRealtime(url, event.request)) {
    // No interceptar: la petición va directo a la red (sin caché).
    return;
  }
  // Solo gestionamos el propio origen.
  if (url.origin !== self.location.origin) return;

  // Navegación: network-first con fallback al shell cacheado (offline shell).
  if (event.request.mode === "navigate") {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          const copy = response.clone();
          caches.open(SHELL_CACHE).then((cache) => cache.put("./index.html", copy));
          return response;
        })
        .catch(() => caches.match("./index.html")),
    );
    return;
  }

  // Assets estáticos: cache-first, poblando el shell cache.
  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) return cached;
      return fetch(event.request).then((response) => {
        if (response.ok && response.type === "basic") {
          const copy = response.clone();
          caches.open(SHELL_CACHE).then((cache) => cache.put(event.request, copy));
        }
        return response;
      });
    }),
  );
});
