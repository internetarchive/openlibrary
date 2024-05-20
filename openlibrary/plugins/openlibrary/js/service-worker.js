import { ExpirationPlugin } from 'workbox-expiration';
import { offlineFallback } from 'workbox-recipes';
import { setDefaultHandler, registerRoute } from 'workbox-routing';
import { NetworkOnly, CacheFirst } from 'workbox-strategies';
import { CacheableResponsePlugin } from 'workbox-cacheable-response';
import { clientsClaim } from 'workbox-core';
import { matchMiscFiles, matchSmallMediumCovers, matchLargeCovers, matchStaticImages, matchStaticBuild, matchArchiveOrgImage } from './service-worker-matchers';

self.skipWaiting();
clientsClaim();

// This is needed for the offline page to show
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

registerRoute(
    matchMiscFiles,
    new CacheFirst({
        cacheName: 'misc-files-cache',
        plugins: [
            new ExpirationPlugin({
                maxAgeSeconds: DAY_SECONDS
            }),
            cacheableResponses
        ],
    })
);

registerRoute(
    matchStaticImages,
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
    matchStaticBuild,
    // This has all the JS and CSS that changes on build
    // We use cache first because it rarely changes
    // But we only cache it for 10 minutes in case of deploy
    // TODO: We should increase this a lot and make it change on deploy (clear it out when the deploy hash changes)
    // it includes a .* at the end because some items have versions ?v=123 after
    new CacheFirst({
        cacheName: 'static-build-cache',
        plugins: [
            new ExpirationPlugin({
                maxAgeSeconds: 60 * 10,
            }),
            cacheableResponses
        ],
    })
)

registerRoute(
    matchSmallMediumCovers,
    // S/M covers - cache 150 of them. They take up no more than 2.25mb of space. There are ~150 covers on the homepage.
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
    matchLargeCovers,
    // L covers - cache 5 of them but with a very short timeout so if you go to a few pages they stay.
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
    matchArchiveOrgImage,
    new CacheFirst({
        cacheName: 'archive-org-images-cache',
        plugins: [
            new ExpirationPlugin({
                maxEntries: 50,
                maxAgeSeconds: DAY_SECONDS,
                purgeOnQuotaError: true,
            }),
            cacheableResponses
        ],
    })
);
