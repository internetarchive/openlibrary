from catalog.get_ia import find_item
from time import sleep
import httplib
import socket

def head(host, path, ia):
    conn = httplib.HTTPConnection(host)
    conn.request("HEAD", path + "/" + ia + "_marc.xml")
    return conn.getresponse()

bad_machine = set()
out = open('has_marc', 'w')
no = open('no_marc', 'w')
later = open('later', 'w')
for line in open('to_load'):
    ia = line[:-1]
    if line.startswith('('):
        print >> no, ia
        continue
    (host, path) = find_item(ia)
    if not host:
        print >> no, ia
        continue
    if host in bad_machine:
        print >> later, ia
        continue
#    print "http://" + host + path + "/" + ia + "_marc.xml"
    try:
        r1 = head(host, path, ia)
    except socket.error:
        print 'socket error'
        print "http://" + host + path + "/" + ia + "_marc.xml"
        print 'try later'
        bad_machine.add(ia)
        print >> later, ia
        continue
        print 'retry in 2 seconds'

    if r1.status in (403, 404):
        print >> no, ia
        continue
    if r1.status != 200:
        print ia, host, path
        print r1.status, r1.reason
        print "http://" + host + path + "/" + ia + "_marc.xml"
    assert r1.status == 200

    print ia
    print >> out, ia
out.close()
later.close()
no.close()
