# a python representation of the Open Library schema
# (run this to produce an html representation)

### questions
# agencies/orgs as "authors" or "contributors"?
# what is meant by the asterisk in "a-z*"?

schema = {

            'author':
            [
                    ('identifier', {
                        'type': 'string',
                        'count': 'multiple',
                        # 'marc_fields': ['100:abcd', '110:ab', '710:ab', '111:acdn', '711:acdn'],
                        'example': "Twain, Mark, 1835-1910",
                        'description': "unique id in some catalog" }),
                    ('name', { 'type': 'string', 'example': "Mark Twain", 'description': "human-readable name" }),
                    ('birth_date', { 'type': 'date', 'example': "1835" }),
                    ('death_date', { 'type': 'date', 'example': "1910" }),
                    ('bio', { 'type': 'text' })
            ],

            'edition':
            [ 
                    ('source_record_loc', {
                        'type': 'string',
                        'count': 'multiple',
                        'example': "marc_records_scriblio_net/part01.dat:29834:543",
                        'description': "a locator for the source record data" }),
                    ('source_record_id', {
                        'type': 'string',
                        'count': 'multiple',
                        'example': "LC:DLC:00000006",
                        'description': "a record identifier that is globally unique and that also can be constructed consistently from the contents of a record and an identifier for its source catalog" }),
                    ('authors', { 'type': 'id-ref', 'count': 'multiple', 'example': 'a/Mark_Twain' }),
                    ('contributions', {
                        'type': 'string',
                        'count': 'multiple',
                        'marc_fields': '700:abcde',
                        'example': 'Illustrated by: Steve Bjorkman' }),
                    ('title', {
                        'type': 'string',
                        'marc_fields': '245:ab',
                        'example': 'The adventures of Tom Sawyer' }),
                    ('by_statement', {
                        'type': 'string',
                        'count': 'multiple',
                        'marc_fields': '245:c',
                        'example': 'Herman Melville ; [illustrated by Barry Moser]' }),
                    ('sort_title', { 'type': 'string', 'example': 'adventures of Tom Sawyer' }),
                    ('other_titles', {
                        'type': 'string',
                        'count': 'multiple',
                        'marc_fields': ['246:a', '730:a-z*', '740:apn' ],
                        'example': "Mark Twain's The Adventures of Tom Sawyer" }),
                    ('work_title', {
                        'type': 'string',
                        'marc_fields': ['240:amnpr', '130:a-z*'],
                        'description': "The 240 \"work title\" is used in the OCLC FRBR algorithm. The 130 is also used, and there should be either a 130 or a 240 in a record, but not both. It would be ideal if we could pick up either for the work title." }),
                    ('edition', {
                        'type': 'string',
                        'marc_fields': '250:ab',
                        'example': '2nd. editon',
                        'description': 'information about this edition' }),
                    ('publisher', {
                        'type': 'string',
                        'marc_fields': '260:b',
                        'example': 'W. W. Norton & Co.' }),
                    ('publish_place', {
                         'type': 'string',
                         'marc_fields': '260:a',
                         'example': 'New York; Boston' }),
                    ('publish_date', { 
                        'type': 'date',
                        'marc_fields': '008:7-10',
                        'example': '2006' }),
                    ('pagination', {
                        'type': 'string',
                        'marc_fields': '300:a',
                        'example': "viii, 383 p. :",
                        'description': "full pagination information" }),
                    ('number_of_pages', {
                        'type': 'int',
                        'example': '237',
                        'marc_fields': '300:a=>biggest_decimal',
                        'description': 'largest decimal found' }),
                    ('subjects', {
                        'type': 'string',
                        'count': 'multiple',
                        'marc_fields': ['600:abcdxvyz', '610:abxvyz', '650:axvyz', '651:axvyz'],
                        'example': 'LCSH: Runaway children -- Fiction' }),
                    ('subject_place', {
                        'type': 'string',
                        'count': 'multiple',
                        'marc_fields': ['651:a', '650:z'],
                        'example': "Venice (Italy)" }),
                    ('subject_time', {
                        'type': 'string',
                        'count': 'multiple',
                        'marc_fields': ['600:y', '650:y'],
                        'example': '20th century' }),
                    ('genre', {
                        'type': 'string',
                        'count': 'multiple',
                        'marc_fields': ['600:v', '650:v', '651:v'],
                        'example': "Biography" }),
                    ('series', {
                        'type': 'string',
                        'count': 'multiple',
                        'marc_fields': ['440:av', '490:av', '830:av' ],
                        'example': "Oxford world's classics" }),
                    ('language', {
                        'type': 'string',
                        'marc_fields': '"ISO: "++008:35-37',
                        'example': 'ISO: tel',
                        'description': "coded or human-readable description of the text's language" }),
                    ('physical_format', { 'type': 'string' }),
                    ('notes', {
                        'type': 'string',
                        'marc_fields': '5??-505-520:a-z',
                        'count': 'multiple' }),
                    ('description', {
                        'type': 'text',
                        'marc_fields': '520:a'
                        }),
                    ('exerpts', { 'type': 'text', 'count': 'multiple' }),
                    ('table_of_contents', {
                        'type': 'text',
                        'count': 'multiple',
                        'marc_fields': '505:art'
                        }),
                    ('cover_image', { 'type': 'url' }),
                    ('scan_contributor', { 'type': 'string' }),
                    ('scan_sponsor', { 'type': 'string' }),
                    ('dewey_number', {
                        'type': 'string',
                        'count': 'multiple',
                        'marc_fields': '082:a',
                        'example': '914.3' }),
                    ('LC_classification', {
                        'type': 'string',
                        'marc_fields': '050:ab',
                        'example': 'BJ1533.C4 L49' }),
                    ('ISBN', {
                        'type': 'string',
                        'marc_fields': ['020:a=>normalize_isbn', '024:a=>normalize_isbn'],
                        'example': '9780393926033',
                        'description': '13-digit ISBN' }),
                    ('UCC_13', { 'type': 'string' }),
                    ('UPC', { 'type': 'string' }),
                    ('ISMN', { 'type': 'string' }),
                    ('DOI', { 'type': 'string' }),
                    ('LCCN', {
                        'type': 'string',
                        'marc_fields': '010:a=>normalize_lccn',
                        'example': "2006285320" }),
                    ('GTIN_14', { 'type': 'string' }),
                    ('oca_identifier', { 'type': 'string', 'example': 'albertgallatinja00stevrich' })
            ]
    }

def print_html ():
        for (typename, fields) in schema.iteritems ():
                print "<p><b>" + typename + "</b></p>"
                print "<table><tbody>"
                print "<tr><th>Field</th><th>Type</th><th>MARC Fields</th><th>Example (Description)</th></tr>"
                for (fname, fspec) in fields:
                        marc_fields = fspec.get ('marc_fields', [])
                        if (type (marc_fields) != list):
                                marc_fields = [marc_fields]
                        print "<tr>"
                        print "<td><b>" + fname + "</b></td>"
                        print "<td>" + fspec['type'] + ((fspec.get ('count', "single") == "multiple" and "*") or '') + "</td>"
                        print "<td>" + ", ".join (marc_fields) + "</td>"
                        print "<td>" + ((fspec.get ('example') and '"' + fspec['example'] + '"') or '') + ((fspec.get ('description') and " <i>(" + fspec['description'] + ")</i>") or '') + "</td>"
                        print "</tr>"
                print "</tbody></table>"

#        for (typename, fields) in schema.iteritems ():
#                print "<p><b>" + typename + "</b></p>"
#                for (fname, fspec) in fields:
#                        print "<li><b>" + fname + "</b> [" + fspec['type'] + ((fspec.get ('count') == 'multiple' and '*') or '') + "] : " + ((fspec.get ('example') and '"' + fspec['example'] + '"') or '') + ((fspec.get ('description') and " <i>(" + fspec['description'] + ")</i>") or '') + "</li>"
#                print "</ul>"
                        
                
if __name__ == "__main__":
        print_html ()

