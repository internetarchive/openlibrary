"""
Create a edition dict that can be passed to catalog.marc.parse.read_edition()

A sample dict looks like this:
{'edition_name': u'3rd ed.', 'pagination': u'xii, 444 p.', 'title': u'A course of pure mathematics', 'publishers': [u'At the University Press'], 'number_of_pages': 444, 'languages': ['eng'], 'publish_date': '1921', 'location': [u'GLAD', u'GLAD'], 'authors': [{'birth_date': u'1877', 'personal_name': u'Hardy, G. H.', 'death_date': u'1947', 'name': u'Hardy, G. H.', 'entity_type': 'person'}], 'by_statement': u'by G.H. Hardy', 'publish_places': [u'Cambridge'], 'publish_country': 'enk'}
"""

class import_edition_builder:    

    def add_string(self, key, val):
        self.edition_dict[key] = val    

    def add_list(self, key, val):
        if key in self.edition_dict:
            self.edition_dict[key].append(val)
        else:
            self.edition_dict[key] = [val]

    def add_author(self, key, val):
        # We don't know birth_date or death_date.
        # Should name and personal_name be the same value?
        author_dict = {
           'personal_name': val, 
           'name': val, 
           'entity_type': 'person'
        }
        self.add_list('authors', author_dict)
    
    def __init__(self):
        self.edition_dict = {}
        self.type_dict = {
            'title'  : self.add_string,
            'author' : self.add_author
        }


    def get_dict(self):
        return self.edition_dict

    def add(self, key, val):
        if not key in self.type_dict:
            print 'invalid key: ' + key
            return
        
        self.type_dict[key](key, val)
