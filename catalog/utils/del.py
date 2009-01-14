from catalog.infostore import get_site
from catalog.olwrite import Infogami
from catalog.read_rc import read_rc

rc = read_rc()
infogami = Infogami(rc['infogami'])

site = get_site()

# throwaway bit of code for deleting bad scan records
# BPL can't scan microtext

keys = site.things({'type': '/type/scan_record', 'locations': '/scanning_center/MBMBN/BPL1MI', 'scan_status': 'NOT_SCANNED'})
while keys:
    for key in keys:
        sr = site.withKey(key)
        print key
        q = {
            'key': key,
            'type': { 'connect': 'update', 'value': '/type/delete' },
        }
        ret = infogami.write(q, comment="can't scan microtext")
        assert ret['status'] == 'ok'
    keys = site.things({'type': '/type/scan_record', 'locations': '/scanning_center/MBMBN/BPL1MI', 'scan_status': 'NOT_SCANNED'})
