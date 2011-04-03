function(doc) {
    var last_modified;
    
    function extend(d1, d2) {
        for (var k in d2) {
            d1[k] = d2[k];
        }
    }
    
    function extend_list(list1, list2) {
        for (var i=0; i<list2.length; i++) {
            list1.push(list2[i]);
        }
        return list1;
    }
    
    function get(d, key, default_value) {
        return d[key] || default_value;
    }
    
    if (!doc.covers || doc.covers.length == 0) {
        return;
    }
    
    if (doc.last_modified && doc.last_modified.value) {
        last_modified = doc.last_modified.value;
    }
        
    var cover_value = {"key": doc.key, "cover": doc.covers[0], 'last_modified': last_modified};
    
    var d = {};
    
    doc.identifiers && extend(d, doc.identifiers);

    d.lccn = get(doc, "lccn", []);
    d.oclc = get(doc, "oclc_numbers", []);
        
    d.isbn = [];
    doc.isbn_10 && extend_list(d.isbn, doc.isbn_10);
    doc.isbn_13 && extend_list(d.isbn, doc.isbn_13);
    
    for (var i=0; i<d.isbn.length; i++) {
        d.isbn[i] = d.isbn[i].replace(/[ -]+/g, "");
    }
    
    for (var name in d) {
        var value = d[name];
        for (var i=0; i<value.length; i++) {
            emit([name, value[i]], cover_value);
        }
    }
    
    doc.ocaid && emit(["ocaid", doc.ocaid], cover_value);

    var olid = doc['key'].split("/")[2];
    emit(["olid", olid], cover_value);
}