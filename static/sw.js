importScripts('https://storage.googleapis.com/workbox-cdn/releases/6.1.5/workbox-sw.js');

if (workbox) {
  console.log(`Yay! Workbox is loaded 🎉`);
  
  //precache using the workbox-cli
  workbox.precaching.precacheAndRoute([{url: '/static/images/logo_OL-err.png', revision:""}]);

  // Offline Page
  workbox.routing.setDefaultHandler(
    new workbox.strategies.NetworkOnly()
  );

  workbox.recipes.offlineFallback({
    pageFallback: '/static/offline.html',
    imageFallback: '/static/images/blank.book.lg.png'
  });

  function matchFunction({ url }) {
    const pages = ['/', '/account/login', '/account', '/account/books', '/account/loans', '/account/books/already-read/stats'];
    return pages.includes(url.pathname);
  }

  // runtime caching as the user visits the page
  workbox.routing.registerRoute(
    matchFunction,
    new workbox.strategies.NetworkFirst({
      cacheName: 'html-cache',
      plugins: [
        new workbox.expiration.ExpirationPlugin({
          // Keep at most 50 entries.
          maxEntries: 50,
          // Don't keep any entries for more than 30 days.
          maxAgeSeconds: 30 * 24 * 60 * 60,
          // Automatically cleanup if quota is exceeded.
          purgeOnQuotaError: true,
        }),
        // only cache if it the request returns 0 or 200 status
        new workbox.cacheableResponse.CacheableResponsePlugin({
          statuses: [0, 200],
        }),
      ],
    })
  );

  // covers png cache
  workbox.routing.registerRoute(
    new RegExp('http://covers.openlibrary.org/b/.+'),
    new workbox.strategies.NetworkFirst({
      cacheName: 'covers-cache',
      plugins: [
        new workbox.expiration.ExpirationPlugin({
          maxEntries: 15,
        }),
        new workbox.cacheableResponse.CacheableResponsePlugin({
          statuses: [0, 200],
        })
      ],
    })
  );

  // works page covers, images from archive.org cache
  workbox.routing.registerRoute(
    new RegExp('https://archive.org/.+'),
    new workbox.strategies.NetworkFirst({
      cacheName: 'archive-cache'
    })
  );

  // asset cache
  workbox.routing.registerRoute(
    /\.(?:js|css|woff)/,
    new workbox.strategies.NetworkFirst({
      cacheName: 'asset-cache',
    })
  );
  
  // images cache (precache)
  workbox.routing.registerRoute(
    /\.(?:png|jpg|jpeg|svg|gif)/,
    new workbox.strategies.CacheFirst({
      cacheName: 'image-cache',
      plugins: [
        new workbox.expiration.ExpirationPlugin({
          maxAgeSeconds: 7 * 24 * 60 * 60,
        })
      ],
    })
  );

  // others page html cache
  workbox.routing.registerRoute(
    new RegExp('/.+'),
    new workbox.strategies.NetworkFirst({
      cacheName: 'other-html-cache',
      plugins: [
        new workbox.expiration.ExpirationPlugin({
          // Due to redirect keep the value 2 times.
          maxEntries: 10,
          // Don't keep any entries for more than 30 days.
          maxAgeSeconds: 30 * 24 * 60 * 60,
          // Automatically cleanup if quota is exceeded.
          purgeOnQuotaError: true,
        }),
        new workbox.cacheableResponse.CacheableResponsePlugin({
          statuses: [0, 200],
        }),
      ],
    })
  );

} else {
  console.log(`Boo! Workbox didn't load 😬`);
}