// Service worker da Kyky: guarda a "casca" do app para abrir rápido no celular.
// A API (/api, /ws) NUNCA é guardada: os dados sempre vêm do PC na hora.
const CACHE = 'kyky-v1';
const CASCA = ['/', '/app.js', '/style.css', '/icon-192.png', '/icon-512.png', '/face.jpg', '/manifest.webmanifest'];

self.addEventListener('install', e => {
  // um arquivo faltando (ex: sem foto) não pode impedir o app de instalar
  e.waitUntil(caches.open(CACHE).then(c => Promise.all(CASCA.map(u => c.add(u).catch(() => {})))).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

// rede primeiro (versão nova sempre que o PC responde); cache só se o PC estiver fora do ar
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== location.origin || url.pathname.startsWith('/api') || url.pathname === '/ws') return;
  e.respondWith(
    fetch(e.request).then(r => {
      if (r.ok) { const copia = r.clone(); caches.open(CACHE).then(c => c.put(e.request, copia)); }
      return r;
    }).catch(() => caches.match(e.request, { ignoreSearch: true }))
  );
});
