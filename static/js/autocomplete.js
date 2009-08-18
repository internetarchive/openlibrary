/** 
  * Setup autocomplete for the element with given id. 
  * 
  * It is setup such that this function is called when the element gets focus for the first time.
  * This function removes the onfocus listener, so this function will not be called for subsequent onfocus events.
  */
function setup_autocomplete(id) {
    // Directly using $('#' + id) may not work as id may have # and . chars.
    var e = document.getElementById(id);

    if (!e)
        return;

    // remove onfocus listener to avoid calling this function again and again.
    e.onfocus = null;

    var elem = $(e);

    var name = elem.attr('ac_name');
    var type = elem.attr('ac_type');
    var property = elem.attr('ac_property');
    var limit = elem.attr("ac_limit");
    
    elem.autocomplete("/getthings", {
        extraParams: {
            type: type,
            property: property
        }, 
        matchCase: true,
        max: limit,
        formatItem: function (row) {
            if (property == "key") 
                return row[0];
            else
                return "<div>" + row[0] + "<br/><div style='font-size: 0.8em;'>" + row[1] + "</div></div>";
	    }
    })
    .result(function(event, data, formatted) {
        var name = $(this).attr('ac_name');
        if ($(this).attr("ac_property") != "key")
            $(document.getElementById('result_' + name)).val(data[1])
    })
    .change(function() {
        // When user selects empty string, set the result to empty
        var name = $(this).attr('ac_name');
        if ($(this).attr("ac_property") != "key")
            $(document.getElementById("result_" + name)).val("");
    });
}

/** 
 * Adds new author with given name.
 * After the author is added, the value of the inputs specified by the id are updated.
 */ 
function new_author(name, id) {
    $.post(
        '/addauthor', 
        {name: name}, 
        function(data, status) {
            if (status == "success") {
                $(document.getElementById("key_" + id)).attr("value", data);
                $(document.getElementById("saved_name_" + id)).attr("value", name);
                 alert("Author added.");
            }
            else {
                alert("Error in creating author: " + status); 
            }
        }, 
        "text"
     );
}

function _log(msg) {
    if (typeof(console) != "undefined")
        console.log(msg);
}

/**
 * Setup freebase suggest for the specified element.
 * Works similar to setup_autocomplete.
 */    
function setup_freebase_suggest(e) {

    _log("BEGIN setup_freebase_suggest: " + e.id);

    // remove onfocus listener to avoid calling this function again and again.
    e.onfocus = null;

    var elem = $(e);
    var name = elem.attr("ac_name");

    elem.freebaseSuggest({
        soft: false, 
        suggest_new: "Create New Author", 
        service_url: "http://" + window.location.host,
        ac_path: '/suggest/search', 
        blurb_path: '/suggest/blurb'
    })
    .bind("fb-select", function(e, data) {
        var name = $(this).attr("ac_name");
        $(document.getElementById("key_" + name)).attr("value", data.id);
        $(document.getElementById("saved_name_" + name)).attr("value", data.name);
    })
    .bind("fb-select-new", function(e, data) {
        var name = $(this).attr("ac_name");
        new_author(data.name, name);
    })
    .bind("change", function() {
        var name = $(this).attr("ac_name");
        if ($.trim($(this).val()) == "") {
            $(document.getElementById('key_' + name)).val("")
            $(document.getElementById('saved_name_' + name)).val("")
        }
    });

    $(document.getElementById('key_' + name)).parents('form')
        .bind("submit", function(e, data) {
            var v1 = $(document.getElementById("saved_name_" + name)).val();
            var v2 = $(document.getElementById("name_" + name)).val();

            if (v1 != v2) {
                $(".fberror", $(document.getElementById("name_" + name)).parent()).show()
                $(document.getElementById("name_" + name)).focus();
                return false;
            }
            return true;
        });

    elem.trigger("focus");
   _log("END setup_freebase_suggest: " + e.id);
    
}

// Freebase urls are of the for /view/$key where as OL urls are just $key. 
// This is a monkey-patch to fix that.
window.freebase.controls.suggest.prototype.freebase_url = function(id, options) {
    //var url = options.service_url + "/view" + this.quote_id(id);
    var url = options.service_url + this.quote_id(id);
    return url;
};
