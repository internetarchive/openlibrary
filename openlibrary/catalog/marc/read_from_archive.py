import urllib2
import xml.etree.ElementTree as et
from MARC21 import MARC21Record
from MARC21Exn import MARC21Exn
from pprint import pprint
from time import sleep

archive_url = "http://archive.org/download/"

def urlopen_keep_trying(url):
    while 1:
        print url
        try:
            return urllib2.urlopen(url)
        except urllib2.URLError:
            pass
        sleep(5)

class FileWrapper(file):
    def __init__(self, part):
        self.fh = urlopen_keep_trying(archive_url + part)
        self.pos = 0
    def read(self, size):
        self.pos += size
        return self.fh.read(size)
    def tell(self):
        return self.pos
    def close(self):
        return self.fh.close()

def files(archive_id):
    url = archive_url + archive_id + "/" + archive_id + "_files.xml"
    tree = et.parse(urlopen_keep_trying(url))
    for i in tree.getroot():
        assert i.tag == 'file'
        name = i.attrib['name']
        if name.endswith('.mrc') or name.endswith('.marc') or name.endswith('.out'):
            yield archive_id + "/" + name

def bad_data(i):
    pass

def read_marc_file(part, f, pos = 0):
    buf = None
    while 1:
        if buf:
            length = buf[:5]
            int_length = int(length)
        else:
            length = f.read(5)
            buf = length
        if length == "":
            break
        assert length.isdigit()
        int_length = int(length)
        if 0 and part == 'marc_western_washington_univ/wwu_bibs.mrc_revrev.mrc':
            if pos == 295782261:
                int_length+=1
            elif pos == 299825918:
                int_length+=5
        data = buf + f.read(int_length - len(buf))
        buf = None
        if data.find('\x1d') == -1:
            data += f.read(40)
            int_length = data.find('\x1d') + 1
            print `data[-40:]`
            assert int_length
            buf = data[int_length:]
            data = data[:int_length]
        assert data.endswith("\x1e\x1d")
        if len(data) < int_length:
            yield (loc, 'bad')
            break
        loc = "%s:%d:%d" % (part, pos, int_length)
        pos += int_length
        if str(data)[6:8] != 'am':
            yield (loc, 'not_book')
            continue
        try:
            rec = MARC21Record(data)
        except IndexError:
            rec = 'bad'
        except TypeError:
            rec = 'bad'
        except ValueError:
            rec = 'bad'
        except EOFError:
            print "EOF"
            print `data`
            rec = 'bad'
        except MARC21Exn:
            rec = 'bad'
        yield (loc, rec)

#archive = [ "unc_catalog_marc", "marc_oregon_summit_records",
#    "marc_university_of_toronto", "marc_miami_univ_ohio",
#archive = [ "marc_western_washington_univ", "marc_boston_college" ]
archive = [ "marc_western_washington_univ" ]
#archive = [ "marc_boston_college" ]
archive = [ "bcl_marc" ]

# marc_university_of_toronto/uoft.marc:2568231948:707
# marc_university_of_toronto/uoft.marc:2571412614:886

# marc_western_washington_univ/wwu_bibs.mrc_revrev.mrc:286075909:955

def check():
    part = 'marc_boston_college/bc_openlibrary.mrc'
    pos = 2147477123
    part = 'marc_western_washington_univ/wwu_bibs.mrc_revrev.mrc'
    pos = 295780665
    pos = 395466242
    pos = 495359719
    pos = 778742194
    pos = 875901953
#    pos = 299825182
#    pos = 298636444
#    pos = 299562947
#    pos = 299702849
#    pos = 303085246
    part = 'marc_records_scriblio_net/part10.dat'
    pos = 99557594
#    ureq = urllib2.Request(archive_url + part, None, {'Range':'bytes=%d-%d'% (pos, pos+1000000000)} )
#    f = urllib2.urlopen(ureq)
    f = urllib2.urlopen(archive_url + part)

    i = 0
    total = 0
    bad_record = []
    not_interesting = 0
    for loc, rec in read_marc_file(part, f, pos):
        total+=1
        if rec == 'not_book':
            not_interesting += 1
            continue
        if rec == 'bad':
            print 'bad:', loc
            bad_record.append(loc)
            continue
    #    if str(rec.leader)[6:8] != 'am':
    #        not_interesting += 1
    #        continue
        i+=1
        if i % 1000 == 0:
            print i, loc

#check()

for archive_id in archive:
    i = 0
    total = 0
    bad_record = []
    not_interesting = 0
    print archive_id
    for part in files(archive_id):
        print part
        f = urlopen_keep_trying(archive_url + part)
        for loc, rec in read_marc_file(part, f):
            total+=1
            if rec == 'not_book':
                not_interesting += 1
                continue
            if rec == 'bad':
                print 'bad:', loc
                bad_record.append(loc)
                continue
            i+=1
            if i % 1000 == 0:
                print i, loc
    for loc in bad_record:
        print loc
    print archive_id, total, i, not_interesting, len(bad_record)
