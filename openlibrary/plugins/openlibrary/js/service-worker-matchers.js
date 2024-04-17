/*
This is a separate file to avoid this error with tests:

    SyntaxError: Cannot use import statement outside a module

    > 1 | import { ExpirationPlugin } from 'workbox-expiration';
*/


export function matchMiscFiles({ url }) {
    const miscFiles = ['/static/favicon.ico', '/static/manifest.json',
        '/static/css/ajax-loader.gif', '/cdn/archive.org/analytics.js',
        '/cdn/archive.org/donate.js', '/static/css/fonts/slick.woff']
    return miscFiles.includes(url.pathname);
}

/**
 * Checks if a given URL includes a small or medium cover.
 *
 * @param {Object} params - The parameters object.
 * @param {URL} params.url - The URL to check.
 * @returns {boolean} - Returns true if the URL indicates a small or medium cover size, otherwise false.
 */
export function matchSmallMediumCovers({url}){
    const regex = /-[SM].jpg$/;
    return regex.test(url.pathname);
}

export function matchLargeCovers({url}){
    const regex = /-L.jpg$/;
    return regex.test(url.pathname);
}

export function matchStaticImages({url}){
    const regex = /^\/images\/|^\/static\/images\//;
    return regex.test(url.pathname);
}

export function matchStaticBuild({url}){
    const regex = /^\/static\/build\/.*(\.js|\.css)/;
    const localhost = url.origin.includes('localhost')
    const gitpod = url.origin.includes('gitpod')
    return !localhost && !gitpod && regex.test(url.pathname);
}
