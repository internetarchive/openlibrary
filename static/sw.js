self.addEventListener('install', e => {
    console.log('Install!!!');
    e.waitUntil(
        caches.open('static').then(cache => {
            return cache.addAll(['/']);
        })
    );
});

self.addEventListener('fetch', e => {
    console.log('SW fetch',e);
    e.respondWith(
        caches.match(e.request).then(response => {
            return response || fetch(e.request);
        })
    );
});
