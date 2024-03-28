import { ExpirationPlugin } from 'workbox-expiration';
import { offlineFallback } from 'workbox-recipes';
import { setDefaultHandler, registerRoute } from 'workbox-routing';
import { CacheFirst, NetworkFirst, NetworkOnly } from 'workbox-strategies';
import {CacheableResponsePlugin} from 'workbox-cacheable-response';
import { clientsClaim } from 'workbox-core';

self.skipWaiting();
clientsClaim();

// Offline Page
setDefaultHandler(
    new NetworkOnly()
);

offlineFallback({
    pageFallback: '/static/offline.html',
    imageFallback: '/static/images/logo_OL-lg.png'
});


const daySeconds = 24 * 60 * 60;
// only cache if it the request returns 0 or 200 status
const cacheableResponses = new CacheableResponsePlugin({
    statuses: [0, 200],
});


// TODO: Talk with Drini about what makes sense here
// Which of these do we actually want to load network first vs show a cached page
function matchFunction({ url }) {
    const pages = ['/', '/account/login', '/account', '/account/books', '/account/loans', '/account/books/already-read/stats'];
    return pages.includes(url.pathname);
}

// runtime caching as the user visits the page
registerRoute(
    matchFunction,
    new NetworkFirst({
        cacheName: 'html-cache',
        plugins: [
            new ExpirationPlugin({
                maxEntries: 50,
                maxAgeSeconds: 30 * 24 * 60 * 60,
                purgeOnQuotaError: true,
            }),
            cacheableResponses
        ],
    })
);

/*
static/images, static/fonts, static/logos - should stay for a long time
static/build/css(and js) - just for 5 minutes because I'm not sure about cache busting on deploy
*/

registerRoute(
    /\/static\/(images|fonts|logos)/,
    new CacheFirst({
        cacheName: 'static-cache-images-fonts-logos',
        plugins: [
            new ExpirationPlugin({
                maxEntries: 150,
                maxAgeSeconds: 7 * daySeconds,
                purgeOnQuotaError: true,
            }),
            cacheableResponses
        ],
    })
)

registerRoute(
    /\/static\/build/,
    new CacheFirst({
        cacheName: 'static-cache-build',
        plugins: [
            new ExpirationPlugin({
                maxAgeSeconds: 60 * 5,
                purgeOnQuotaError: true,
            }),
            cacheableResponses
        ],
    })
)

/*
Covers:
S/M covers - cache 150 of them to take up no more than 2.25mb of space.
L covers - cache 5 of them but with a very short timeout so if you're looking at a few they don't keep loading but they take up much of your storage.
Original covers (with no letter) - save as above, just in case
*/

// Neither of these have the starting / because they don't come from the same origin
// These urls could be domain agnostic if we want them to work locally but it would make them less readable
const smallMediumCovers = new RegExp('.+(S|M).jpg');
// This includes large covers and original size because of the ? in "L?"
const largeCovers = new RegExp('.+L?.jpg');
registerRoute(
    smallMediumCovers,
    new CacheFirst({
        cacheName: 'covers-cache-small-medium',
        plugins: [
            new ExpirationPlugin({
                maxEntries: 150,
                purgeOnQuotaError: true,
            }),
            cacheableResponses
        ],
    })
);

registerRoute(
    largeCovers,
    new CacheFirst({
        cacheName: 'covers-cache-large',
        plugins: [
            new ExpirationPlugin({
                maxEntries: 5,
                maxAgeSeconds: daySeconds / 24,
                purgeOnQuotaError: true,
            }),
            cacheableResponses
        ],
    })
);

// cache all other images that happen to be on the page
// This will only be same origin
registerRoute(
    /\.(?:png|jpg|jpeg|svg|gif)/,
    new CacheFirst({
        cacheName: 'image-cache',
        plugins: [
            new ExpirationPlugin({
                maxEntries: 50,
                maxAgeSeconds: 7 * daySeconds,
                purgeOnQuotaError: true
            })
        ],
    })
);

// cache all other requests on the same origin
registerRoute(
    /\/*/,
    new NetworkFirst({
        cacheName: 'other-html-cache',
        plugins: [
            new ExpirationPlugin({
                maxEntries: 150,
                purgeOnQuotaError: true,
            }),
            cacheableResponses
        ],
    })
);
