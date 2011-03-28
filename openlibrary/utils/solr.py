"""Python library for accessing Solr.
"""
import urlparse
import urllib, urllib2
import re
import web
import simplejson

def urlencode(d, doseq=False):
    """There is a bug in urllib when used with unicode data.

        >>> d = {"q": u"\u0C05"}
        >>> urllib.urlencode(d)
        'q=%E0%B0%85'
        >>> urllib.urlencode(d, doseq=True)
        'q=%3F'

    This function encodes all the unicode strings in utf-8 before passing them to urllib.
    """
    def utf8(d):
        if isinstance(d, dict):
            return dict((utf8(k), utf8(v)) for k, v in d.iteritems())
        elif isinstance(d, list):
            return [utf8(v) for v in d]
        else:
            return web.safestr(d)

    return urllib.urlencode(utf8(d), doseq=doseq)

class Solr:
    def __init__(self, base_url):
        self.base_url = base_url
        self.host = urlparse.urlsplit(self.base_url)[1]

    def escape(self, query):
        r"""Escape special characters in the query string

            >>> solr = Solr("")
            >>> solr.escape("a[b]c")
            'a\\[b\\]c'
        """
        chars = r'+-!(){}[]^"~*?:\\'
        pattern = "([%s])" % re.escape(chars)
        return web.re_compile(pattern).sub(r'\\\1', query)

    def select(self, query, fields=None, facets=None,
               rows=None, start=None,
               doc_wrapper=None, facet_wrapper=None,
               **kw):
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
        params['start'] = start or 0

        if fields:
            params['fl'] = ",".join(fields)

        if facets:
            params['facet'] = "true"
            params['facet.field'] = []

            for f in facets:
                if isinstance(f, dict):
                    name = f.pop("name")
                    for k, v in f.items():
                        params["f.%s.facet.%s" % (name, k)] = v
                else:
                    name = f
                params['facet.field'].append(name)

        url = self.base_url + "/select?" + urlencode(params, doseq=True)
        data = urllib2.urlopen(url).read()
        return self._parse_solr_result(
            simplejson.loads(data), 
            doc_wrapper=doc_wrapper, 
            facet_wrapper=facet_wrapper)

    def _parse_solr_result(self, result, doc_wrapper, facet_wrapper):
        response = result['response']

        doc_wrapper = doc_wrapper or web.storage
        facet_wrapper = facet_wrapper or (lambda name, value, count: web.storage(locals()))

        d = web.storage()
        d.num_found = response['numFound']
        d.docs = [doc_wrapper(doc) for doc in response['docs']]

        if 'facet_counts' in result:
            d.facets = {}
            for k, v in result['facet_counts']['facet_fields'].items():
                d.facets[k] = [facet_wrapper(k, value, count) for value, count in web.group(v, 2)]

        if 'highlighting' in result:
            d.highlighting = result['highlighting']

        if 'spellcheck' in result:
            d.spellcheck = result['spellcheck']

        return d

    def _prepare_select(self, query):
        def escape(v):
            # TODO: improve this
            return v.replace('"', r'\"').replace("(", "\\(").replace(")", "\\)")

        def escape_value(v):
            if isinstance(v, tuple): # hack for supporting range
                return "[%s TO %s]" % (escape(v[0]), escape(v[1]))
            elif isinstance(v, list): # one of 
                return "(%s)" % " OR ".join(escape_value(x) for x in v)
            else:
                return '"%s"' % escape(v)

        if isinstance(query, dict):
            op = query.pop("_op", "AND")
            if op.upper() != "OR":
                op = "AND"
            op = " " + op + " "

            q = op.join('%s:%s' % (k, escape_value(v)) for k, v in query.items())
        else:
            q = query
        return q

if __name__ == '__main__':
    import doctest
    doctest.testmod()
