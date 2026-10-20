// Service worker mínimo: só existe para o app ser instalável (PWA).
// Não guarda cache — o Vite dev já serve tudo na hora.
self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", (event) => {
  // Só rede; deixa o navegador cuidar do cache.
  event.respondWith(fetch(event.request));
});
