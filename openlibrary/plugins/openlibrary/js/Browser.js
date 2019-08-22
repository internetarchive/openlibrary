/** @typedef {{ [param: string]: string }} UrlParams  */

/**
 * Convert url parameters to an object
 * @param {String} urlSearch everything after (and including) the '?' of the url
 * @returns {UrlParams}
 */
export function getJsonFromUrl(urlSearch) {
    const query = urlSearch.substr(1);
    const result = {};
    if (query) {
        query.split('&').forEach(part => {
            const item = part.split('=');
            result[item[0]] = decodeURIComponent(item[1]);
        });
    }
    return result;
}

/**
 * @param {String} url
 * @param {String} parameter name of param to remove
 * @returns {String}
 */
export function removeURLParameter(url, parameter) {
    var urlparts = url.split('?');
    var prefix = urlparts[0];
    var query, paramPrefix, params, i;
    if (urlparts.length >= 2) {
        query = urlparts[1];
        paramPrefix = `${encodeURIComponent(parameter)}=`;
        params = query.split(/[&;]/g);

        //reverse iteration as may be destructive
        for (i = params.length; i-- > 0;) {
            //idiom for string.startsWith
            if (params[i].lastIndexOf(paramPrefix, 0) !== -1) {
                params.splice(i, 1);
            }
        }

        url = prefix + (params.length > 0 ? `?${params.join('&')}` : '');
        return url;
    } else {
        return url;
    }
}
