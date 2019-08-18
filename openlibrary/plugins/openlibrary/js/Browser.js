/** @typedef {{ [param: string]: string }} UrlParams  */

/**
 * Convert url parameters to an object
 * @returns {UrlParams}
 */
export function getJsonFromUrl() {
    var query = location.search.substr(1);
    var result = {};
    query.split('&').forEach(function(part) {
        var item = part.split('=');
        result[item[0]] = decodeURIComponent(item[1]);
    });
    return result;
}

export function change_url(query) {
    var getUrl = window.location;
    var baseUrl = `${getUrl.protocol}//${getUrl.host
    }/${getUrl.pathname.split('/')[1]}`;
    window.history.pushState({
        'html': document.html,
        'pageTitle': `${document.title} ${query}`,
    }, '', `${baseUrl}?id=${query}`);
}

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
