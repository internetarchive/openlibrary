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

;(function() {

function Subject(data, options) {
    var defaults = {
        pagesize: 12
    }
    this.settings = $.extend(defaults, options);

    this.filter = {};
    this.has_fulltext = "false";
    this.sort = "editions";
    
    this.init(data);
    this._data = data;
}

window.Subject = Subject;

// Implementation of Python urllib.urlencode in Javascript.
function urlencode(query) {
    var parts = [];
    for (var k in query) {
        parts.push(k + "=" + query[k]);
    }
    return parts.join("&");
}

function slice(array, begin, end) {
    var a = [];
    for (var i=begin; i < Math.min(array.length, end); i++) {
        a.push(array[i]);
    }
    return a;
}

$.extend(Subject.prototype, {
    
    init: function(data) {
        $.log(["init", this, arguments]);
        
        $.extend(this, data);    
        this.page_count = Math.ceil(this.work_count / this.settings.pagesize);
        this.epage_count = Math.ceil(this.ebook_count / this.settings.pagesize);
        
        // cache already visited pages
        //@@ Can't this be handled by HTTP caching?
        this._pages = {};
        if (this.has_fulltext != "true")
            this._pages[0] = {"works": slice(data.works, 0, this.settings.pagesize)};
    
        // TODO: initialize additional pages when there are more works.
    },

    bind: function(name, callback) {
        $(this).bind(name, callback);
    },

    getPageCount: function() {
        return this.has_fulltext == "true"? this.epage_count : this.page_count;
    },

    loadPage: function(pagenum, callback) {
        var offset = pagenum * this.settings.pagesize;
        var limit = this.settings.pagesize;
    
        if (offset > this.bookCount) {
            callback && callback([]);
        }
    
        if (this._pages[pagenum]) {
            callback(this._pages[pagenum]);
        }
        else {
            var page = this;
            
            var params = {
                "limit": limit,
                "offset": offset,
                "has_fulltext": this.has_fulltext,
                "sort": this.sort
            }
            $.extend(params, this.filter);
            
            var url = this.key + ".json?" + urlencode(params);
            var t = this;
                
            $.getJSON(url, function(data) {
                t._pages[pagenum] = data;
                callback(data);
            });
        }
    },
    
    _ajax: function(params, callback) {
        params = $.extend({"limit": this.settings.pagesize, "offset": 0}, this.filter, params);
        var url = this.key + ".json?" + urlencode(params);
        $.getJSON(url, callback);
    },

    setFilter: function(filter, callback) {
        for (var k in filter) {
            if (filter[k] == null) {
                delete filter[k];
            }
        }
        this.filter = filter;
                
        var _this = this;
        this._ajax({"details": "true"}, function(data) {
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
});

})();