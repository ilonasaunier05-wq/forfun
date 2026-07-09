const CACHE = 'ilona-os-v3-cache';
const ASSETS = ['./','./index.html','./manifest.webmanifest','./assets/favicon.svg','./assets/icons/icon-192.png','./assets/icons/icon-512.png'];
self.addEventListener('install', event => { event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(ASSETS))); self.skipWaiting(); });
self.addEventListener('activate', event => { event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))); self.clients.claim(); });
self.addEventListener('fetch', event => { event.respondWith(caches.match(event.request).then(cached => cached || fetch(event.request).catch(() => caches.match('./index.html')))); });
