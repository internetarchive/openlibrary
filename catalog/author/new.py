from catalog.olwrite import Infogami
from catalog.read_rc import read_rc
import sys

rc = read_rc()
infogami = Infogami(rc['infogami'])
infogami.login('EdwardBot', rc['EdwardBot'])

name = sys.argv[1]

q = {
    'create': 'unless_exists',
    'name': name,
    'personal_name': name
    'entity_type': 'person',
    'key': infogami.new_key('/type/author'),
    'type': '/type/author',
}

print infogami.write(q, comment='create author')
