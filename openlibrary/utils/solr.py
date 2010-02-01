"""Python library for accessing Solr.
"""
import urlparse
import urllib, urllib2
import web
import simplejson

class Solr:
    def __init__(self, base_url):
        self.base_url = base_url
        self.host = urlparse.urlsplit(self.base_url)[1]
        
    def select(self, query, fields=None, facets=None, rows=None, offset=None, doc_wrapper=None, facet_wrapper=None, **kw):
        """Execute a solr query.
        
        query can be a string or a dicitonary. If query is a dictionary, query
        is constucted by concatinating all the key-value pairs with AND condition.
        """
        params = {'wt': 'json'}
        
        for k, v in kw.items():
            # convert keys like facet_field to facet.field
            params[k.replace('_', '.')] = v
        
        params['q'] = self._prepare_select(query)
        if rows is not None:
            params['rows'] = rows
        params['offset'] = offset or 0
        
        if fields:
            params['fl'] = ",".join(fields)
        
        if facets:
            params['facet'] = "true"
            params['facet.field'] = facets
            
        url = self.base_url + "/select?" + urllib.urlencode(params, doseq=True)
        print url
        data = urllib2.urlopen(url).read()
        return self._parse_solr_result(simplejson.loads(data), doc_wrapper=doc_wrapper, facet_wrapper=facet_wrapper)
        
    def _parse_solr_result(self, result, doc_wrapper, facet_wrapper):
        response = result['response']
        
        doc_wrapper = doc_wrapper or web.storage
        facet_wrapper = facet_wrapper or (lambda value, count: web.storage(locals()))
        
        d = web.storage()
        d.num_found = response['numFound']
        d.docs = [doc_wrapper(doc) for doc in response['docs']]
        
        if 'facet_counts' in result:
            d.facets = {}
            for k, v in result['facet_counts']['facet_fields'].items():
                d.facets[k] = [facet_wrapper(value, count) for value, count in web.group(v, 2)]
                
        if 'highlighting' in result:
            d.highlighting = result['highlighting']
            
        if 'spellcheck' in result:
            d.spellcheck = result['spellcheck']
                
        return d
        
    def _prepare_select(self, query):
        def escape(v):
            return v.replace('"', r'\"')
            
        if isinstance(query, dict):
            q = " AND ".join('%s:"%s"' % (k, escape(v)) for k, v in query.items())
        else:
            q = query
        return q