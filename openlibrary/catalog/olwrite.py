import web
from infogami.infobase import client
import simplejson
import sys

web.ctx.ip = '127.0.0.1'

class Infogami:
    def __init__(self, host, sitename='openlibrary.org'):
        self.conn = client.connect(type='remote', base_url=host)
        self.sitename = sitename

    def _request(self, path, method, data):
        out = self.conn.request(self.sitename, path, method, data)
        out = simplejson.loads(out)
        if out['status'] == 'fail':
            raise Exception(out['message'])
        return out

    def login(self, username, password):
        return self._request('/account/login', 'POST', dict(username=username, password=password))

    def write(self, query, comment='', machine_comment=None):
        query = simplejson.dumps(query)
        return self._request('/write', 'POST', dict(query=query, comment=comment, machine_comment=machine_comment))

    def new_key(self, type):
        return self._request('/new_key', 'GET', dict(type=type))['result']

def add_to_database(infogami, q, loc):
# sample return
#    {'status': 'ok', 'result': {'updated': [], 'created': ['/b/OL13489313M']}}

    for a in (i for i in q.get('authors', []) if 'key' not in i):
        a['key'] = infogami.new_key('/type/author')

    q['key'] = infogami.new_key('/type/edition')
    ret = infogami.write(q, comment='initial import', machine_comment=loc)
    assert ret['status'] == 'ok'
    keys = [ i for i in ret['result']['created'] if i.startswith('/b/')]
    try:
        assert len(keys) == 1 or keys[0] == q['key']
    except AssertionError:
        print q
        print ret
        print keys
        raise
    return q['key']
