const CACHE_NAME = 'urbinati-analytics-v1';

self.addEventListener('install', (e) => {
    self.skipWaiting();
});

self.addEventListener('activate', (e) => {
    e.waitUntil(clients.claim());
});

self.addEventListener('fetch', (e) => {
    // Permite que Flask maneje todas las consultas en tiempo real
    return;
});