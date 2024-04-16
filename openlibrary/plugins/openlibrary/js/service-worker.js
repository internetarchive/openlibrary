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
// afaik it only contains https://testing.openlibrary.org/static/css/ajax-loader.gif
// oh also fonts https://testing.openlibrary.org/static/css/fonts/slick.ttf
// TODO we should move this to the static/images folder



// These almost never change
https://openlibrary.org/static/images/
https://openlibrary.org/images/



// covers
https://covers.openlibrary.org/a/id/6257045-M.jpg // author covers
https://covers.openlibrary.org/a/olid/OL2838765A-M.jpg // random dot images
https://covers.openlibrary.org/b/id/1852327-M.jpg // book covers
https://covers.openlibrary.org/w/id/14348537-M.jpg // redirects to IA with a 302

// IA profile picture
https://archive.org/services/img/@raybb
https://archive.org/services/img/brand00ibse // these are covers



// Done
https://openlibrary.org/static/build/*.js
https://openlibrary.org/static/build/*.css

// Misc

https://openlibrary.org/static/favicon.ico
https://openlibrary.org/static/manifest.json
https://testing.openlibrary.org/static/css/ajax-loader.gif

*/

function matchMiscFiles({ url }) {
    const miscFiles = ['/static/favicon.ico', '/static/manifest.json',
        '/static/css/ajax-loader.gif', '/cdn/archive.org/analytics.js',
        '/cdn/archive.org/donate.js', '/static/css/fonts/slick.woff']
    return miscFiles.includes(url.pathname);
}
registerRoute(
    matchMiscFiles,
    new CacheFirst({
        cacheName: 'misc-files-cache',
        plugins: [
            new ExpirationPlugin({
                maxAgeSeconds: DAY_SECONDS * 30
            }),
            cacheableResponses
        ],
    })
);


registerRoute(
    new RegExp('/images/|/static/images/'),
    new CacheFirst({
        cacheName: 'static-images-cache',
        plugins: [
            new ExpirationPlugin({
                maxEntries: 100,
                maxAgeSeconds: DAY_SECONDS * 365,
            }),
        ],
    })
);

registerRoute(
    /\/static\/build\/.*(\.js|\.css).*/,
    // This has all the JS and CSS that changes on build
    // We use cache first because it rarely changes
    // But we only cache it for 5 minutes in case of deploy
    // TOOD: We should increase this a lot and make it change on deploy (clear it out when the deploy hash changes)
    // it includes a .* at the end because some items have versions ?v=123 after
    new CacheFirst({
        cacheName: 'static-build-cache',
        plugins: [
            new ExpirationPlugin({
                maxAgeSeconds: 60 * 5, // Five minutes
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
        cacheName: 'covers-small-medium-cache',
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
        cacheName: 'covers-large-cache',
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

registerRoute(
    ({ url })=> url.href.startsWith('https://archive.org/services/img/'),
    new CacheFirst({
        cacheName: 'archive-org-images-cache',
        plugins: [
            new ExpirationPlugin({
                maxEntries: 50,
                maxAgeSeconds: DAY_SECONDS * 1,
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
        cacheName: 'other-cache',
        plugins: [
            new ExpirationPlugin({
                maxEntries: 50,
                purgeOnQuotaError: true,
            }),
            cacheableResponses
        ],
    })
);
