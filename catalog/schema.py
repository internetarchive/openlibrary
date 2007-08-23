# a python representation of the Open Library schema
# (run this to produce an html representation)

schema = {

            'author':
            {
                    'name': { 'type': 'string' },
                    'birth_date': { 'type': 'date' },
                    'death_date': { 'type': 'date' },
                    'bio': { 'type': 'text' },
            },

            'edition':
            {
                    'source_name': { 'type': 'string' },
                    'source_record_pos': { 'type': 'int' },
                    'authors': { 'type': 'id-ref', 'count': 'multiple', 'example': 'a/Mark_Twain' },
                    'contributions': { 'type': 'string', 'count': 'multiple', 'example': 'Illustrated by: Steve Bjorkman' },
                    'title': { 'type': 'string', 'example': 'The adventures of Tom Sawyer' },
		    'by_statement': { 'type': 'string', 'count': 'multiple', 'example': 'Herman Melville ; [illustrated by Barry Moser]' },
                    'sort_title': { 'type': 'string', 'example': 'adventures of Tom Sawyer' },
		    'other_titles': { 'type': 'string', 'count': 'multiple', 'example': "Mark Twain's The Adventures of Tom Sawyer" },
                    'edition': { 'type': 'string', 'example': '2nd. editon', 'description': 'information about this edition' },
                    'publisher': { 'type': 'string', 'example': 'W. W. Norton & Co.' },
                    'publish_place': { 'type': 'string', 'example': 'New York; Boston' },
                    'publish_date': { 'type': 'date', 'example': '2006' },
                    'number_of_pages': { 'type': 'int', 'example': '237', 'description': 'largest decimal found' },
                    'subjects': { 'type': 'string', 'count': 'multiple', 'example': 'LCSH: Runaway children -- Fiction' },
		    'series': { 'type': 'string', 'count': 'multiple', 'example': "Oxford world's classics" },
                    'language': { 'type': 'string', 'example': 'iso: tel', 'description': "coded or human-readable description of the text's language" },
                    'physical_format': { 'type': 'string' },
		    'notes': { 'type': 'string', 'count': 'multiple' },
                    'description': { 'type': 'text' },
		    'exerpts': { 'type': 'text', 'count': 'multiple' },
		    'table_of_contents': { 'type': 'text', 'count': 'multiple' },
                    'cover_image': { 'type': 'url' },
                    'scan_contributor': { 'type': 'string' },
                    'scan_sponsor': { 'type': 'string' },
		    'dewey_number': { 'type': 'string', 'count': 'multiple', 'example': '914.3' },
		    'lc_classification': { 'type': 'string', 'example': 'BJ1533.C4 L49' },
                    'ISBN': { 'type': 'string', 'example': '9780393926033', 'description': '13-digit ISBN' },
                    'UCC_13': { 'type': 'string' },
                    'UPC': { 'type': 'string' },
                    'ISMN': { 'type': 'string' },
                    'DOI': { 'type': 'string' },
                    'LCCN': { 'type': 'string' },
                    'GTIN_14': { 'type': 'string' },
                    'oca_identifier': { 'type': 'string', 'example': 'albertgallatinja00stevrich' }
            }
    }

def print_html ():
	for (typename, fields) in schema.iteritems ():
		print "<p><b>" + typename + "</b></p>"
		print "<ul>"
		for (fname, fspec) in fields.iteritems ():
			print "<li><b>" + fname + "</b> [" + fspec['type'] + ((fspec.get ('count') == 'multiple' and '*') or '') + "] : " + ((fspec.get ('example') and '"' + fspec['example'] + '"') or '') + ((fspec.get ('description') and " <i>(" + fspec['description'] + ")</i>") or '') + "</li>"
		print "</ul>"
			
		
if __name__ == "__main__":
	print_html ()

