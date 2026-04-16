// Minimal service worker — caches the app shell so Ralph VC opens
// instantly and survives flaky cellular. Network-first for the
// /v1/orchestrate API so chat replies never go stale.
//
// Authored by Chase Eddies <source@distillative.ai>.

const CACHE = 'ralphvc-shell-v1';
const SHELL = [
  './',
  './index.html',
  './manifest.webmanifest',
  './icons/icon-180.png',
  './icons/icon-512.png',
];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (url.pathname.includes('/v1/orchestrate') || url.pathname.includes('/healthz')) {
    // Always go to network for API calls.
    return;
  }
  // Cache-first for the shell.
  e.respondWith(
    caches.match(e.request).then((cached) => cached || fetch(e.request))
  );
});
