def map(doc):
    last_modified = doc.get("last_modified", {}).get("value", "")
    covers = doc.get("covers") or [-1]
    
    cover_value = {"cover": covers[0], 'last_modified': last_modified}
    
    d = {}
    d.update(doc.get("identifiers", {}))
    
    d.update({
        "isbn": doc.get("isbn_10", [])  + doc.get("isbn_13", []),
        "lccn": doc.get("lccn", []),
        "oclc": doc.get("oclc_numbers", []),
    })
    
    d['isbn'] = [isbn.upper().replace("-", "") for isbn in d['isbn']]
    
    d['ia'] = [s[len("ia:"):] for s in doc.get("source_records", []) if s.startswith("ia:")]
    if 'ocaid' in doc and doc['ocaid'] not in d['ia']:
        d['ia'].append(doc['ocaid'])
    
    d['olid'] = [doc['key'].split("/")[-1]]
    
    f = open("/tmp/couch.log", 'a')
    print >> f, doc['key'], d
    print >> f, cover_value
    f.flush()

    for name, values in d.items():
        for v in values:
            yield [name, v], cover_value
