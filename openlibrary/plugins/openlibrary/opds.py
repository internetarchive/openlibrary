"""
OPDS helper class.
A lightweight version of github.com/internetarchive/bookserver
"""

import lxml.etree as ET
from infogami.infobase.utils import parse_datetime

class OPDS():
    xmlns_atom    = 'http://www.w3.org/2005/Atom'
    xmlns_dcterms = 'http://purl.org/dc/terms/'
    xmlns_opds    = 'http://opds-spec.org/'
    xmlns_rdvocab = 'http://RDVocab.info/elements/'
    xmlns_bibo    = 'http://purl.org/ontology/bibo/'
    xmlns_xsi     = 'http://www.w3.org/2001/XMLSchema-instance'
    

    nsmap = {
        None     : xmlns_atom,
        'dcterms': xmlns_dcterms,
        'opds'   : xmlns_opds,
        'rdvocab': xmlns_rdvocab,
        'bibo'   : xmlns_bibo,
        'xsi'    : xmlns_xsi
    }

    atom          = "{%s}" % xmlns_atom
    dcterms       = "{%s}" % xmlns_dcterms
    opdsNS        = "{%s}" % xmlns_opds
    rdvocab       = "{%s}" % xmlns_rdvocab
    bibo          = "{%s}" % xmlns_bibo
    xsi           = "{%s}" % xmlns_xsi
    
    fileExtMap = {
        'pdf'  : 'application/pdf',
        'epub' : 'application/epub+zip',
        'mobi' : 'application/x-mobipocket-ebook'
    }
    
    ebookTypes = ('application/pdf',
                  'application/epub+zip',
                  'application/x-mobipocket-ebook'
    )
    
    # create_text_element()
    #___________________________________________________________________________
    def create_text_element(self, parent, name, value):
        element = ET.SubElement(parent, name)
        element.text = value
        return element

    # add()
    #___________________________________________________________________________
    def add(self, name, value, attrs={}):
        element = self.create_text_element(self.root, name, value)
        for a in attrs:
            element.attrib[a] = attrs[a]

    # add_list()
    #___________________________________________________________________________
    def add_list(self, name, values, prefix='', attrs={}):
        if isinstance(values, list) or isinstance(values, tuple):
            for v in values:
                self.add(name, prefix+unicode(v), attrs)
        elif values:
            self.add(name, prefix+unicode(values), attrs)

    # add_author()
    #___________________________________________________________________________
    def add_author(self, name, uri=None):
        element = ET.SubElement(self.root, 'author')
        self.create_text_element(element, 'name', name)
        if uri:
            self.create_text_element(element, 'uri', uri)
        return element

    # create_rel_link()
    #___________________________________________________________________________
    def create_rel_link(self, parent, rel, absurl, type='application/atom+xml', title=None):
        if None == parent:
            parent = self.root
            
        element = ET.SubElement(parent, 'link')
        element.attrib['rel']  = rel
        element.attrib['type'] = type
        element.attrib['href'] = absurl;
        if title:
            element.attrib['title'] = title;

        return element            
            
    # to_string()
    #___________________________________________________________________________
    def to_string(self):
        return ET.tostring(self.root, pretty_print=True)
        
    # create_root()
    #___________________________________________________________________________
    def create_root(self, root_name):
        ### TODO: add updated element and uuid element
        opds = ET.Element(OPDS.atom + root_name, nsmap=OPDS.nsmap)                    

        return opds

    # __init__()
    #___________________________________________________________________________    
    def __init__(self, root_name="feed"):

        self.root = self.create_root(root_name)

class OPDSEntry(OPDS):

    # add_category()
    #___________________________________________________________________________
    def add_category(self, term, label):
        element = ET.SubElement(self.root, 'category')
        element.attrib['term']  = term
        element.attrib['label'] = label
        return element

    # add_indirect_acq()
    #___________________________________________________________________________
    def add_indirect_acq(self, parent, type):
        element = ET.SubElement(parent, self.opdsNS+'indirectAcquisition')
        element.attrib['type'] = type
        return element
                
    # add_acquisition_links()
    #___________________________________________________________________________
    def add_acquisition_links(self, book, collection):
        if not book.ocaid:
            return
        
        if 'inlibrary' in collection or 'lendinglibrary' in collection:
            available_loans = book.get_available_loans()
            loan_types = [loan['resource_type'] for loan in available_loans]
            got_epub = 'epub' in loan_types
            got_pdf  = 'pdf' in loan_types
            
            if got_epub or got_pdf:
                link = self.create_rel_link(None, 'http://opds-spec.org/acquisition/borrow', 'http://openlibrary.org'+book.url('/borrow'), 'text/html')
                indirect_acq = self.add_indirect_acq(link, 'application/vnd.adobe.adept+xml')
                if got_epub:
                    self.add_indirect_acq(indirect_acq, 'application/epub+zip')
                if got_pdf:
                    self.add_indirect_acq(indirect_acq, 'application/pdf')
        elif 'printdisabled' not in collection:
            self.create_rel_link(None, 'http://opds-spec.org/acquisition/open-access', 'http://www.archive.org/download/%s/%s.pdf'%(book.ocaid, book.ocaid), 'application/pdf')
            self.create_rel_link(None, 'http://opds-spec.org/acquisition/open-access', 'http://www.archive.org/download/%s/%s.epub'%(book.ocaid, book.ocaid), 'application/epub+zip')

    # add_rel_links()
    #___________________________________________________________________________
    def add_rel_links(self, book, work):
        links = []
        if work:
            self.create_rel_link(None, 'related', 'http://openlibrary.org'+work.key, 'text/html', 'Open Library Work')

        for name, values in book.get_identifiers().multi_items():
            for id in values:
                if id.url and name not in ['oclc_numbers', 'lccn', 'ocaid']: #these go in other elements
                    self.create_rel_link(None, 'related', id.url, 'text/html', 'View on '+id.label)

    # __init__()
    #___________________________________________________________________________    
    def __init__(self, book):

        self.root = self.create_root('entry')

        bookID = book.key
        atomID = 'http://openlibrary.org' + bookID + '.opds'
        title = book.title
        if book.subtitle:
            title += " " + book.subtitle
        updated = parse_datetime(book.last_modified).strftime('%Y-%m-%dT%H:%M:%SZ')
    
        work = book.works and book.works[0]
    
        if work:
            authors  = work.get_authors()
            subjects = work.get_subjects()
        else:
            authors  = book.get_authors()  
            subjects = book.get_subjects()
            
        if book.pagination:
            pages = book.pagination
        else:
            pages = book.number_of_pages
    
        # the collection and inlibrary check is coped from databarWork.html
        collection = set()
        meta_fields = book.get_ia_meta_fields()
        if meta_fields:
            collection = meta_fields.get('collection', [])
            contrib = meta_fields.get('contributor')
            if 'inlibrary' in collection and 'inlibrary' in ctx.features:
                library = get_library()

        coverLarge = book.get_cover_url('L')
        coverThumb = book.get_cover_url('S')
                    
        self.add('id', atomID)
        self.create_rel_link(None, 'self', atomID)
        self.create_rel_link(None, 'alternate', 'http://openlibrary.org'+book.url(), 'text/html')
        self.add('title', title)
        self.add('updated', updated)
        
        for a in authors:
            self.add_author(a.name, 'http://openlibrary.org'+a.url())
        
        self.add_list(self.dcterms + 'publisher', book.publishers)
        self.add_list(self.rdvocab + 'placeOfPublication', book.publish_places)
        self.add_list(self.dcterms + 'issued', book.publish_date)
        self.add_list(self.dcterms + 'extent', pages)
        self.add_list(self.rdvocab + 'dimensions', book.physical_dimensions)
        self.add_list(self.bibo    + 'edition', book.edition_name)
        
        for subject in subjects:
            self.add_category('/subjects/'+subject.lower().replace(' ', '_').replace(',',''), subject)
    
        self.add_list('summary', book.description)
        self.add_list(self.rdvocab + 'note', book.notes)
    
        for lang in book.languages:
            self.add_list(self.dcterms + 'language', lang.code)
    
        self.add_list(self.dcterms + 'identifier', book.key,     'http://openlibrary.org', {self.xsi+'type':'dcterms:URI'})
        self.add_list(self.dcterms + 'identifier', book.ocaid,   'http://www.archive.org/details/', {self.xsi+'type':'dcterms:URI'})
        self.add_list(self.dcterms + 'identifier', book.isbn_10, 'urn:ISBN:', {self.xsi+'type':'dcterms:ISBN'})
        self.add_list(self.dcterms + 'identifier', book.isbn_13, 'urn:ISBN:', {self.xsi+'type':'dcterms:ISBN'})
        self.add_list(self.bibo + 'oclcnum', book.oclc_numbers)
        self.add_list(self.bibo + 'lccn', book.lccn)
        
        if coverLarge:
            self.create_rel_link(None, 'http://opds-spec.org/image', coverLarge, 'image/jpeg')
        if coverThumb:
            self.create_rel_link(None, 'http://opds-spec.org/image/thumbnail', coverThumb, 'image/jpeg')

        self.add_acquisition_links(book, collection)
        self.add_rel_links(book, work)        
