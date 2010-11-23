"""Improved CouchDB client.

Unlike the couchdb python library, this returns an iterator view rows instead of a list.
"""

import simplejson

import couchdb.client
from couchdb.client import Row

class Database(couchdb.client.Database):
    def view(self, name, wrapper=None, **options):
        if not name.startswith('_'):
            design, name = name.split('/', 1)
            name = '/'.join(['_design', design, '_view', name])
        return PermanentView(self.resource(*name.split('/')), name,
                             wrapper=wrapper)(**options)

class ViewResults(couchdb.client.ViewResults):
    def _fetch(self):
        data = self.view._exec(self.options)
        wrapper = self.view.wrapper or Row
        
        #self._rows = [wrapper(row) for row in data['rows']]
        self._rows = (wrapper(row) for row in data['rows'])
        
        self._total_rows = data.get('total_rows')
        self._offset = data.get('offset', 0)

class PermanentView(couchdb.client.PermanentView):
    def _exec(self, options):
        if 'keys' in options:
            options = options.copy()
            keys = {'keys': options.pop('keys')}
            _, _, data = self.resource.post(body=keys,
                                                 **self._encode_options(options))
        else:
            _, _, data = self.resource.get(**self._encode_options(options))

        return self.parse_view_result(data)
        
    def __call__(self, **options):
        return ViewResults(self, options)
        
    def parse_view_result(self, rawdata):
        rawdata = iter(rawdata)
        header = rawdata.next().strip()
        
        if not header.endswith("]}"):
            header += "]}"
        data = simplejson.loads(header)
        data["rows"] = self._parse_rows(rawdata)
        return data
        
    def _parse_rows(self, lineiter):
        for row in lineiter:
            row = row.strip()
            if not row or row == "]}":
                break
            if row != ",":
                yield simplejson.loads(row)
