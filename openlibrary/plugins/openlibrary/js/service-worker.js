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


const HOUR_SECONDS = 60 * 60;
const DAY_SECONDS = 24 * HOUR_SECONDS;
// only cache if it the request returns 0 or 200 status
const cacheableResponses = new CacheableResponsePlugin({
    statuses: [0, 200],
});

/*

Lets make a nice little list of things to cache.

// These only change on deploy
https://openlibrary.org/static/css/
// includes https://testing.openlibrary.org/static/css/ajax-loader.gif
https://openlibrary.org/static/build/*.js
https://openlibrary.org/static/build/*.css



// These almost never change
https://openlibrary.org/static/images/
https://openlibrary.org/static/favicon.ico

// covers
https://covers.openlibrary.org/a/id/6257045-M.jpg // author covers
https://covers.openlibrary.org/a/olid/OL2838765A-M.jpg // random dot images
https://covers.openlibrary.org/b/id/1852327-M.jpg // book covers
https://covers.openlibrary.org/w/id/14348537-M.jpg // redirects to IA with a 302

// IA profile picture
https://archive.org/services/img/@raybb



*?

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
                maxAgeSeconds: 7 * DAY_SECONDS,
                purgeOnQuotaError: true,
            }),
            cacheableResponses
        ],
    })
)

registerRoute(
    /\/static\/build/,
    new CacheFirst({
        cacheName: 'static-build-cache',
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
                maxAgeSeconds: HOUR_SECONDS,
                purgeOnQuotaError: true,
            }),
            cacheableResponses
        ],
    })
);

// cache all other requests on the same origin
registerRoute(
    /.*/,
    new NetworkFirst({
        cacheName: 'other-html-cache',
        plugins: [
            new ExpirationPlugin({
                maxEntries: 50,
                purgeOnQuotaError: true,
            }),
            cacheableResponses
        ],
    })
);
