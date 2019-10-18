// Subject class
//
// Usage:
//      var subject = Subject({
//              "key": "/subjects/Love",
//              "name": "Love",
//              "work_count": 1234,
//              "works": [...]
//          },
//          {
//              "pagsize": 12
//          });
//

export function Subject(data, options) {
    var defaults;
    options = options || {};
    defaults = {
        pagesize: 12
    }
    this.settings = $.extend(defaults, options);
    this.slug = data.name.replace(/\s+/g, '-').toLowerCase();
    this.filter = {};
    this.published_in = options.published_in ? options.published_in : undefined;
    this.has_fulltext = options.readable ? 'true' : 'false';
    this.sort = options.sort ? options.sort : 'editions';

    this.init(data);
    this._data = data;
}

// Implementation of Python urllib.urlencode in Javascript.
export function urlencode(query) {
    var parts = [];
    var k;
    for (k in query) {
        parts.push(`${k}=${query[k]}`);
    }
    return parts.join('&');
}
export function renderTag(tag, keyvals, child) {
    var html = `<${tag} `;
    var key, val;
    for (key in keyvals) {
        val =  keyvals[key];
        if (val == '') {
            html += `${key} `;
        } else {
            html += `${key}="${val}" `;
        }
    }
    if (tag === 'img') {
        return `${html}/>`;
    }
    html += '>';
    if (child) {
        html += child;
    }
    html += `</${tag}>`;
    return html;
}

export function slice(array, begin, end) {
    var a = [];
    var i;
    for (i=begin; i < Math.min(array.length, end); i++) {
        a.push(array[i]);
    }
    return a;
}

Subject.prototype = {

    init: function(data) {
        $.extend(this, data);
        this.page_count = Math.ceil(this.work_count / this.settings.pagesize);
        this.epage_count = Math.ceil(this.ebook_count / this.settings.pagesize);

        // cache already visited pages
        //@@ Can't this be handled by HTTP caching?
        this._pages = {};
        if (this.has_fulltext != 'true')
            this._pages[0] = {works: slice(data.works, 0, this.settings.pagesize)};

    // TODO: initialize additional pages when there are more works.
    },

    bind: function(name, callback) {
        $(this).bind(name, callback);
    },

    getPageCount: function() {
        return this.has_fulltext == 'true'? this.epage_count : this.page_count;
    },

    renderWork: function(work) {
        var authors = [];
        var author;
        var ed, titlestring, bookcover_url, format, bookread_url, html
        for (author in work.authors)
            authors.push(work.authors[author].name);
        ed = `edition${work.edition_count > 1 ? 's' : ''}`;
        titlestring = `${work.title} by ${authors.join(', ')
        } (${work.edition_count} ${ed})`;
        bookcover_url = `//covers.openlibrary.org/b/id/${work.cover_id}-M.jpg`;
        format = work.public_scan ? 'public' : (work.printdisabled && !work.ia_collection.includes('inlibrary')) ? 'daisy' : 'borrow';
        bookread_url = work.public_scan ?
            (`//archive.org/stream/${work.ia}?ref=ol`) :
            `/borrow/ia/${work.ia}`;
        html = renderTag('div', {class: 'coverMagic'},
            renderTag('span', {
                itemtype: 'https://schema.org/Book',
                itemscope: ''},
            renderTag('div', {class: 'SRPCover'},
                renderTag('a', {href: work.key, title: titlestring,
                    'data-ol-link-track': `subject-${this.slug}`},
                renderTag('img', {src: bookcover_url, itemprop: 'image',
                    alt: titlestring, class: 'cover'}))) +
        renderTag('div', {class: 'coverEbook'},
            (format === 'public' ?
                renderTag('a', {href: bookread_url, title: 'Read online',
                    class: 'cta-btn--available cta-btn'}, 'Read') :
                renderTag('a', {
                    href: bookread_url,
                    title: 'Read this book',
                    class: 'cta-btn cta-btn--available',
                    'data-ocaid': work.ia,
                    'data-key': work.key
                })))));
        return html;
    },

    loadPage: function(pagenum, callback) {
        var offset = pagenum * this.settings.pagesize;
        var limit = this.settings.pagesize;
        var params, key, url, t;

        if (offset > this.bookCount) {
            callback && callback([]);
        }

        if (this._pages[pagenum]) {
            callback(this._pages[pagenum]);
        }
        else {
            params = {
                limit: limit,
                offset: offset,
                has_fulltext: this.has_fulltext,
                sort: this.sort
            }
            if (this.published_in) {
                params.published_in = this.published_in;
            }
            $.extend(params, this.filter);

            key = this.key.replace(/\s+/g, '_');
            url = `${key}.json?${urlencode(params)}`;
            t = this;

            $.getJSON(url, function(data) {
                t._pages[pagenum] = data;
                callback(data);
            });
        }
    },

    _ajax: function(params, callback) {
        var key, url;
        params = $.extend({limit: this.settings.pagesize, offset: 0},
            this.filter, params);
        key = this.key.replace(/\s+/g, '_');
        url = `${key}.json?${urlencode(params)}`;
        $.getJSON(url, callback);
    },

    setFilter: function(filter, callback) {
        var k, _this;
        for (k in filter) {
            if (filter[k] == null) {
                delete filter[k];
            }
        }
        this.filter = filter;

        _this = this;
        this._ajax({details: 'true'}, function(data) {
            _this.init(data);
            callback && callback();
        });
    },

    setSort: function(sort_order) {
        if (this.sort == sort_order) {
            return; // shouldn't happen
        }
        this.sort = sort_order;
        this._pages = {};
    },

    setFulltext: function(has_fulltext) {
        if (this.has_fulltext == has_fulltext) {
            return;
        }
        this.has_fulltext = has_fulltext;
        this._pages = {};
    },

    addFilter: function(filter, callback) {
        this.setFilter($.extend({}, this.filter, filter), callback);
    },

    reset: function(callback) {
        this.filter = {};
        this.init(this._data);
        callback && callback();
    }
};
