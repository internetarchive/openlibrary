# a python representation of the Open Library schema
# (run this to produce an html representation)

### questions
# agencies/orgs as "authors" or "contributors"?
# "020 $z - Canceled/invalid ISBN"
# dewey decimal (and universal decimal?): need edition number?
# strip punctuation:
#       - title: "/", ";", ":"
#       - publisher, publish_place
# for our physical_format field, how about 245:h (Medium) and 300:c (Dimensions) ?
# tag all 6XX fields as "LCSH"?

# 024: A standard number or code published on an item which cannot be
# accommodated in another field (e.g., field 020 (International Standard Book
# Number), 022 (International Standard Serial Number) , and 027 (Standard
# Technical Report Number)). The type of standard number or code is identified
# in the first indicator position or in subfield $2 (Source of number or code).

# Following is a python datastructure representing the field-schema for
# bibliographic items in ThingDB.  Where the `count` attribute is not
# specified, its value is `'single'`.  The types `string`, `text`, `url` (and
# perhaps `date`) may all be stored as "strings" in ThingDB, but the
# distinction here may help to render those strings appropriately in the UI.

schema_ordered = {

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
                        'title': "Source Record Locator",
                        'type': 'string',
                        'count': 'multiple',
                        'example': "marc_records_scriblio_net/part01.dat:29834:543",
                        'description': "a locator for the source record data" }),
                    ('source_record_id', {
                        'title': "Source Record Id",
                        'type': 'string',
                        'count': 'multiple',
                        'example': "LC:DLC:00000006",
                        'description': "a record identifier that is globally unique and that also can be constructed consistently from the contents of a record and an identifier for its source catalog" }),
                    ('author_identifier', {
                        'title': "Author Identifier",
                        'type': 'string',
                        'count': 'multiple',
                        'marc_fields': ['100:abcd author_id', '110:ab author_id', '111:acdn author_id'],
                        'example': "Twain, Mark, 1835-1910",
                        'description': "unique author id in some catalog" }),
                    # ('authors', { 'type': 'id-ref', 'count': 'multiple', 'example': 'a/Mark_Twain' }),
                    ('contributions', {
                        'title': "Contributions",
                        'type': 'string',
                        'count': 'multiple',
                        'marc_fields': ['700:abcde', '710:ab', '711:acdn'],
                        'example': 'Illustrated by: Steve Bjorkman' }),
                    ('title', {
                        'title': "Title",
                        'type': 'string',
                        'marc_fields': '245:ab clean_name',
                        'example': 'The adventures of Tom Sawyer' }),
                    ('by_statement', {
                        'title': "By Statement",
                        'type': 'string',
                        'count': 'multiple',
                        'marc_fields': '245:c',
                        'example': 'Herman Melville ; [illustrated by Barry Moser]' }),
                    ('sort_title', {
                        'title': "Title for sorting",
                        'type': 'string',
                        'example': 'adventures of Tom Sawyer'
                        }),
                    ('other_titles', {
                        'title': "Other Titles",
                        'type': 'string',
                        'count': 'multiple',
                        'marc_fields': ['246:a', '730:a-z', '740:apn' ],
                        'example': "Mark Twain's The Adventures of Tom Sawyer" }),
                    ('work_title', {
                        'title': "Work Title",
                        'type': 'string',
                        'marc_fields': ['240:amnpr', '130:a-z'],
                        'description': "The 240 \"work title\" is used in the OCLC FRBR algorithm. The 130 is also used, and there should be either a 130 or a 240 in a record, but not both. It would be ideal if we could pick up either for the work title." }),
                    ('edition', {
                        'title': "Edition",
                        'type': 'string',
                        'marc_fields': '250:ab',
                        'example': '2nd. editon',
                        'description': 'information about this edition' }),
                    ('publisher', {
                        'title': "Publisher",
                        'type': 'string',
                        'marc_fields': '260:b clean_name',
                        'example': 'W. W. Norton & Co.' }),
                    ('publish_place', {
                        'title': "Publish Place",
                        'type': 'string',
                        'count': 'multiple',
                        'marc_fields': '260:a clean',
                        'example': 'New York' }),
                    ('publish_date', { 
                        'title': "Publish Date",
                        'type': 'date',
                        'marc_fields': '008:7-10',
                        'example': '2006' }),
                    ('pagination', {
                        'title': "Pagination",
                        'type': 'string',
                        'marc_fields': '300:a',
                        'example': "viii, 383 p. :",
                        'description': "full pagination information" }),
                    ('number_of_pages', {
                        'title': "Number of Pages",
                        'type': 'int',
                        'example': '237',
                        'marc_fields': '300:a biggest_decimal',
                        'description': 'largest decimal found' }),
                    ('subjects', {
                        'title': "Subjects",
                        'type': 'string',
                        'count': 'multiple',
                        'marc_fields': ['600:abcd--x--v--y--z',
                                        '610:ab--x--v--y--z',
                                        '650:a--x--v--y--z',
                                        '651:a--x--v--y--z'],
                        'example': 'Runaway children -- Fiction' }),
                    ('subject_place', {
                        'title': "Subject Places",
                        'type': 'string',
                        'count': 'multiple',
                        'marc_fields': ['651:a*', '650:z*'],
                        'example': "Venice (Italy)" }),
                    ('subject_time', {
                        'title': "Subject Times",
                        'type': 'string',
                        'count': 'multiple',
                        'marc_fields': ['600:y*', '650:y*'],
                        'example': '20th century' }),
                    ('genre', {
                        'title': "Genre",
                        'type': 'string',
                        'count': 'multiple',
                        'marc_fields': ['600:v*', '650:v*', '651:v*'],
                        'example': "Biography" }),
                    ('series', {
                        'title': "Series Information",
                        'type': 'string',
                        'count': 'multiple',
                        'marc_fields': ['440:av', '490:av', '830:av' ],
                        'example': "Oxford world's classics" }),
                    ('language', {
                        'title': "Language",
                        'type': 'string',
                        'marc_fields': '"ISO:" 008:35-37 +',
                        'example': 'ISO:tel',
                        'description': "coded or human-readable description of the text's language" }),
                    ('physical_format', {
                        'title': "Physical Format",
                        'type': 'string',
                        'count': 'multiple',
                        'marc_fields': '245:h' }),
                    ('notes', {
                        'title': "Notes",
                        'type': 'string',
                        'count': 'multiple',
                        'marc_fields': '500-599!505!520:a-z',
                        }),
                    ('description', {
                        'title': "Description",
                        'type': 'text',
                        'marc_fields': '520:a'
                        }),
                    ('exerpts', { 'type': 'text', 'count': 'multiple' }),
                    ('table_of_contents', {
                        'title': "Table of Contents",
                        'type': 'text',
                        'count': 'multiple',
                        'marc_fields': '505:art'
                        }),
                    ('cover_image', { 'type': 'url' }),
                    ('scan_contributor', { 'type': 'string' }),
                    ('scan_sponsor', { 'type': 'string' }),
                    ('dewey_number', {
                        'title': "Dewey Decimal Classification",
                        'type': 'string',
                        'count': 'multiple',
                        'marc_fields': '082:a',
                        'example': '914.3' }),
                    ('LC_classification', {
                        'title': "Library of Congress Classification",
                        'type': 'string',
                        'count': 'multiple',
                        'marc_fields': '050:ab',
                        'example': 'BJ1533.C4 L49' }),
                    ('ISBN', {
                        'type': 'string',
                        'count': 'multiple',
                        'marc_fields': ['020:a normalize_isbn', '024:a normalize_isbn'],
                        'example': '9780393926033',
                        'description': 'a 13-digit ISBN' }),
                    ('UCC_13', { 'type': 'string' }),
                    ('UPC', { 'type': 'string' }),
                    ('ISMN', { 'type': 'string' }),
                    ('DOI', { 'type': 'string' }),
                    ('LCCN', {
                        'type': 'string',
                        'marc_fields': '010:a normalize_lccn',
                        'example': "2006285320" }),
                    ('GTIN_14', { 'type': 'string' }),
                    ('oca_identifier', { 'type': 'string', 'example': 'albertgallatinja00stevrich' })
            ]
    }

schema = {}
for (typename, ordered_fields) in schema_ordered.iteritems ():
    fields = {}
    for (fname, fspec) in ordered_fields:
        fields[fname] = fspec
    schema[typename] = fields

def print_html ():
        for (typename, fields) in schema_ordered.iteritems ():
                print "<p><b>" + typename + "</b></p>"
                print "<table border=\"1\"><tbody>"
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

def print_template (typename):
        print "<dl class=\"metadata\">"
        for (fname, fspec) in schema_ordered[typename]:
                title = fspec.get ('title', fname)
                description = fspec.get ('description', "")
                multiple = (fspec.get ('count', "single") == "multiple")

                print "$if page.d.get('%s'):" % fname
                print "\t<dt title=\"%s\"><b>%s</b></dt>" % (description, title)
                if multiple:
                        print "\t$for v in page.d.get('%s'): <dd>$v</dd>" % fname
                else:
                        print "\t<dd>$page.%s</dd>" % fname
        print "</dl>"
                
if __name__ == "__main__":
        from sys import argv
        if len (argv) == 3:
                if argv[1] == "template":
                        typename = argv[2]
                        print_template (typename)
        else:
                print_html ()

