
function setup_autocomplete(e) {
    var e = $(e);
    
    var name = e.attr('ac_name');
    var type = e.attr('ac_type');
    var property = e.attr('ac_property');
    var limit = e.attr("ac_limit");
    
    e.autocomplete("/getthings", {
        extraParams: {
            type: type,
            property: property
        }, 
        matchCase: true,
        max: limit,
        minChars: 2,
        formatItem: function (row) {
            if (property == "key") 
                return row[0];
            else
                return "<div style='marging: 0px; padding: 0px;'>" + row[0] + "<br/><div style='font-size: 0.8em;'>" + row[1] + "</div></div>";
	    }
    })
    .result(function(event, data, formatted) {
        var name = $(this).attr("ac_name");
        $(document.getElementById('result_' + name)).val(data[1])
    });
}

// Freebase urls are of the for /view/$key where as OL urls are just $key. 
// This is a monkey-patch to fix that.
window.freebase.controls.suggest.prototype.freebase_url = function(id, options) {
    //var url = options.service_url + "/view" + this.quote_id(id);
    var url = options.service_url + this.quote_id(id);
    return url;
};
