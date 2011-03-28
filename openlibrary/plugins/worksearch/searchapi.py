"""Leagacy editions search API at /api/search.
"""
import simplejson
import traceback
import web

from infogami.utils import delegate
from infogami import config

from openlibrary.utils import solr

class search_api:
    error_val = {'status':'error'}
    def GET(self):
        i = web.input(q = None,
                      rows = 20,
                      offset = 0,
                      format = None,
                      callback = None,
                      prettyprint=False,
                      _unicode=False)        
        offset = int(i.get('offset', '0') or 0)
        rows = int(i.get('rows', '0') or 20)
        
        result = self.process(i.q, rows=rows, offset=offset)
        return self.format(result, i.prettyprint, i.callback)
        
    def process(self, q, rows, offset):
        try:
            query = simplejson.loads(q).get('query')
            query = self.process_query(query)
            
            result = self.solr_select(query)
            return {"status": "ok", "result": result}
        except Exception:
            traceback.print_exc()
            return {'status':'error'}
            
    def get_editions_solr(self):
        c = config.get("plugin_worksearch")
        host = c and c.get('edition_solr')
        return host and solr.Solr("http://" + host + "/solr/editions")
    
    def solr_select(self, query):
        solr = self.get_editions_solr()
        response = solr.select(query)
        docs = response['docs']
        return ["/books/" + doc["key"] for doc in docs]
            
    def process_query(self, query):
        if ":" in query:
            # The new editions solr indexed both isbn_10 and isbn_13 as isbn.
            query = query.replace("isbn_10:", "isbn:")
            query = query.replace("isbn_13:", "isbn:")
        else:
            query = SimpleQueryProcessor().process(query)
        return query

    def format(self, val, prettyprint=False, callback=None):
        if prettyprint:
            json = simplejson.dumps(val, indent = 4)
        else:
            json = simplejson.dumps(val)

        if callback is None:
            return json
        else:
            return '%s(%s)'% (callback, json)

class SimpleQueryProcessor:
    """Utility to expand search queries.

        >>> SimpleQueryProcessor().process("hello")
        '(title:hello^100 OR author_name:hello^15 OR subject:hello^10 OR language:hello^10)'
        >>> SimpleQueryProcessor().process("hello world") #doctest: +NORMALIZE_WHITESPACE
        '(title:hello^100 OR author_name:hello^15 OR subject:hello^10 OR language:hello^10)
         (title:world^100 OR author_name:world^15 OR subject:world^10 OR language:world^10)'
    """
    def process(self, query):
        query = web.utf8(query)
        tokens = query.split(' ')
        return " ".join(self.process_token(t) for t in tokens if t.strip())

    def process_token(self, token):
        return '(title:%s^100 OR author_name:%s^15 OR subject:%s^10 OR language:%s^10)' % (token, token, token, token)
        
def setup():
    from infogami.plugins.api import code as api
    api.add_hook('search', search_api)