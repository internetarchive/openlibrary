from gevent import sleep, spawn, spawn_link_exception, monkey
from gevent.queue import JoinableQueue
from gevent.socket import socket, AF_INET, SOCK_DGRAM, SOL_UDP, SO_BROADCAST, timeout
from gevent.pool import Pool
from datetime import datetime
monkey.patch_socket()
import re, httplib, json, sys
from time import time
from collections import defaultdict
from lxml.etree import Element, tostring, parse, fromstring
import urllib2
from unicodedata import normalize

scan_list = '/home/edward/scans/book_data_2010-12-09'
input_count = 0
current_book = None
find_item_book = None
item_queue = JoinableQueue(maxsize=100)
solr_queue = JoinableQueue(maxsize=1000)
locator_times = []
#item_and_host_queue = JoinableQueue(maxsize=10000)
t0 = time()
total = 1936324
items_processed = 0
items_skipped = 0
solr_ia_status = None
solr_error = False
host_queues = defaultdict(lambda: JoinableQueue(maxsize=1000))
solr_host = 'localhost:8983'
#solr_pool = Pool(4)
re_href = re.compile('href="([^"]+)"')
host_threads = {}
load_log = open('/1/log/index_inside', 'w')
good_log = open('/1/log/book_good', 'a')
bad_log = open('/1/log/book_bad', 'a')
done_count = 0
good_count = 0
bad_count = 0
two_threads_per_host = True


# http://www.archive.org/services/find_file.php?file=bostonharborunce00bost&loconly=1

def done(ia, was_good):
    global done_count, good_count, bad_count
    book_log = good_log if was_good else bad_log
    if was_good:
        good_count += 1
    else:
        bad_count += 1
    print >> book_log, ia
    done_count += 1
    #book_log.flush()

re_ia_host = re.compile('^ia(\d+).us.archive.org$')
def use_secondary(host):
    m = re_ia_host.match(host)
    num = int(m.group(1))
    return host if num % 2 else 'ia%d.us.archive.org' % (num + 1)

def use_primary(host):
    m = re_ia_host.match(host)
    num = int(m.group(1))
    return host if num % 2 == 0 else 'ia%d.us.archive.org' % (num - 1)

def urlread_keep_trying(url):
    for i in range(3):
        try:
            return urllib2.urlopen(url).read()
        except urllib2.HTTPError, error:
            if error.code == 404:
                #print "404 for '%s'" % url
                raise
            else:
                print 'error:', error.code, error.msg
            pass
        except httplib.BadStatusLine:
            print 'bad status line'
        except httplib.IncompleteRead:
            print 'incomplete read'
        except urllib2.URLError:
            pass
        print url, "failed"
        sleep(2)
        print "trying again"

def find_abbyy(dir_html, ia):
    if 'abbyy' not in dir_html:
        return

    for line in dir_html.splitlines():
        m = re_href.search(line)
        if not m:
            continue
        href = m.group(1)
        if href.endswith('abbyy.gz') or href.endswith('abbyy.zip') or href.endswith('abbyy.xml'):
            return href
        elif 'abbyy' in href:
            print 'bad abbyy:', `href, ia`

nl_meta = 'meta: '
re_meta = re.compile('meta: ([a-z]+) (\d+)')
def read_text_from_node(host):
    global items_processed
    while True:
        #print 'host_queues[%s].get()' % host
        num, ia, path = host_queues[host].get()

        filename = ia + '_abbyy'
        filename_gz = filename + '.gz'

        url = 'http://%s/%s' % (host, path)
        dir_html = urlread_keep_trying('http://%s/%s' % (host, path))
        if not dir_html:
            done(ia, False)
            host_queues[host].task_done()
            continue

        filename = find_abbyy(dir_html, ia)
        if not filename:
            done(ia, False)
            host_queues[host].task_done()
            continue

        #print 'host_queues[%s].get() done'
        url = 'http://%s/~edward/abbyy_to_text.php?ia=%s&path=%s&file=%s' % (host, ia, path, filename)
        reply = urlread_keep_trying(url)
        if not reply or 'language not currently OCRable' in reply[:200]:
            done(ia, False)
            host_queues[host].task_done()
            continue
        #index = reply.rfind(nl_page_count)
        index = reply.rfind(nl_meta)
        if index == -1:
            print 'bad reply'
            print url
            done(ia, False)
            host_queues[host].task_done()
            continue
        last_nl = reply.rfind('\n')
        assert last_nl != -1
        body = reply[:index].decode('utf-8')
        assert reply[-1] == '\n'
        try:
            (lang, page_count) = re_meta.match(reply[index:-1]).groups()
        except:
            print 'searching:', index, `reply[index:-1]`
            raise
        assert page_count.isdigit()
        if body != '':
            meta_xml = urlread_keep_trying('http://%s%s/%s_meta.xml' % (host, path, ia))
            root = fromstring(meta_xml)
            collection = [e.text for e in root.findall('collection')]

            #print 'solr_queue.put((ia, body, page_count))'
            solr_queue.put((ia, body, lang, page_count, collection))
            #print 'solr_queue.put() done'
            items_processed += 1
        else:
            done(ia, False)
        host_queues[host].task_done()

#def index_items():
#    while True:
#        (num, ia, host, path) = item_and_host_queue.get()
#
#        host_queues[host].put((num, ia, path, filename))
#        if host not in host_threads:
#            host_threads[host] = spawn_link_exception(read_text_from_node, host)
#        item_and_host_queue.task_done()

def add_to_item_queue():
    global input_count, current_book, items_skipped
    skip = False
    check_for_existing = False
    items_done = set(line[:-1] for line in open('/1/log/book_good'))
    items_done.update(line[:-1] for line in open('/1/log/book_bad'))
    for line in open('/home/edward/scans/book_data_2010-12-09'):
        input_count += 1
        ia = line[:-1]
        if ia.startswith('WIDE-2010'):
            continue
        if ia in items_done:
            items_skipped += 1
            continue

        current_book = ia
        if check_for_existing:
            url = 'http://' + solr_host + '/solr/inside/select?indent=on&wt=json&rows=0&q=ia:' + ia
            num_found = json.load(urllib2.urlopen(url))['response']['numFound']
            if num_found != 0:
                continue

        #print 'item_queue.put((input_count, ia))'
        item_queue.put((input_count, ia))
        #print 'item_queue.put((input_count, ia)) done'

re_loc = re.compile('^(ia\d+\.us\.archive\.org):(/\d+/items/(.*))$')

class FindItemError(Exception):
    pass

def find_item(ia):
    s = socket(AF_INET, SOCK_DGRAM, SOL_UDP)
    s.setblocking(1)
    s.settimeout(2.0)
    s.setsockopt(1, SO_BROADCAST, 1)
    s.sendto(ia, ('<broadcast>', 8010))
    for attempt in range(5):
        (loc, address) = s.recvfrom(1024)
        m = re_loc.match(loc)

        ia_host = m.group(1)
        ia_path = m.group(2)
        if m.group(3) == ia:
            return (ia_host, ia_path)
        else:
            print ia, '!=', m.group(3), 'retry'
    raise FindItemError

def web_find_item(ia):
    reply = urlread_keep_trying('http://www.archive.org/services/find_file.php?file=%s&loconly=1' % ia)
    if not reply:
        return
        raise FindItemError
    root = fromstring(reply)
    assert root.tag == 'results'
    if len(root) == 0:
        raise FindItemError
    assert root[0].tag == 'location'
    return (root[0].get('host'), root[0].get('dir'))

def run_find_item():
    global find_item_book
    while True:
        (num, ia) = item_queue.get()
        find_item_book = ia
        #print 'find_item:', ia
        t0_find_item = time()
        try:
            try:
                (host, path) = find_item(ia)
            except timeout:
                (host, path) = web_find_item(ia)
        #except (timeout, FindItemError):
        except FindItemError:
            t1_find_item = time() - t0_find_item
            #print 'fail find_item:', ia, t1_find_item
            item_queue.task_done()
            done(ia, False)
            continue
        t1_find_item = time() - t0_find_item
        #print 'find_item:', ia, t1_find_item
        if len(locator_times) == 100:
            locator_times.pop(0)
        locator_times.append((t1_find_item, host))

        host_queues[host].put((num, ia, path))
        if host not in host_threads:
            if two_threads_per_host:
                host_threads[host] = [ \
                    spawn_link_exception(read_text_from_node, host), \
                    spawn_link_exception(read_text_from_node, host)]
            else:
                host_threads[host] = spawn_link_exception(read_text_from_node, host)
        item_queue.task_done()

def add_field(doc, name, value):
    field = Element("field", name=name)
    field.text = normalize('NFC', unicode(value))
    doc.append(field)

def build_doc(ia, body, page_count):
    doc = Element('doc')
    add_field(doc, 'ia', ia)
    add_field(doc, 'body', body)
    add_field(doc, 'body_length', len(body))
    add_field(doc, 'page_count', page_count)
    return doc


def run_solr_queue(queue_num):
    def log(line):
        print >> load_log, queue_num, datetime.now().isoformat(), line
        load_log.flush()
    global solr_ia_status, solr_error
    while True:
        log('solr_queue.get()')
        (ia, body, lang, page_count, collection) = solr_queue.get()
        log(ia + ' - solr_queue.get() done')
        add = Element("add")
        esc_body = normalize('NFC', body.replace(']]>', ']]]]><![CDATA[>'))
        r = '<add commitWithin="10000000"><doc>\n'
        r += '<field name="ia">%s</field>\n' % ia
        r += '<field name="body_%s"><![CDATA[%s]]></field>\n' % (lang, esc_body)
        r += '<field name="body_length">%s</field>\n' % len(body)
        r += '<field name="page_count">%s</field>\n' % page_count
        for c in collection:
            r += '<field name="collection">%s</field>\n' % c
        r += '</doc></add>\n'

        #doc = build_doc(ia, body, page_count)
        #add.append(doc)
        #r = tostring(add).encode('utf-8')
        url = 'http://%s/solr/inside/update' % solr_host
        #print '       solr post:', ia
        log(ia + ' - solr connect and post')
        h1 = httplib.HTTPConnection(solr_host)
        h1.connect()
        h1.request('POST', url, r.encode('utf-8'), { 'Content-type': 'text/xml;charset=utf-8'})
        #print '    request done:', ia
        response = h1.getresponse()
        #print 'getresponse done:', ia
        response_body = response.read()
        #print '        response:', ia, response.reason
        h1.close()
        log(ia + ' - read solr connect and post done')
        if response.reason != 'OK':
            print r[:100]
            print '...'
            print r[-100:]

            print 'reason:', response.reason
            print 'reason:', response_body
            solr_error = (response.reason, response_body)
            break
        assert response.reason == 'OK'
        solr_ia_status = ia
        log(ia + ' - solr_queue.task_done()')
        done(ia, True)
        solr_queue.task_done()
        log(ia + ' - solr_queue.task_done() done')

def status_thread():
    sleep(2)
    while True:
        run_time = time() - t0
        if solr_error:
            print '***solr error***'
            print solr_error
        print 'run time:            %8.2f minutes' % (float(run_time) / 60)
        print 'input queue:         %8d' % item_queue.qsize()
        #print 'after find_item:     %8d' % item_and_host_queue.qsize()
        print 'solr queue:          %8d' % solr_queue.qsize()

        #rec_per_sec = float(input_count - items_skipped) / run_time
        if done_count:
            rec_per_sec = float(done_count) / run_time
            remain = total - (done_count + items_skipped)

            sec_left = remain / rec_per_sec
            hours_left = float(sec_left) / (60 * 60)
            print 'done count:          %8d (%.2f items/second)' % (done_count, rec_per_sec)
            print '%8d good (%8.2f%%)   %8d bad (%8.2f%%)' % (good_count, ((float(good_count) * 100) / done_count), bad_count, ((float(bad_count) * 100) / done_count))
            print '       %8.2f%%       %8.2f hours left (%.1f days/left)' % (((float(items_skipped + done_count) * 100.0) / total), hours_left, hours_left / 24)

        #print 'items processed:     %8d (%.2f items/second)' % (items_processed, float(items_processed) / run_time)
        print 'current book:              ', current_book
        print 'most recently feed to solr:', solr_ia_status

        host_count = 0
        queued_items = 0
        for host, host_queue in host_queues.items():
            if not host_queue.empty():
                host_count += 1
            qsize = host_queue.qsize()
            queued_items += qsize
        print 'host queues:         %8d' % host_count
        print 'items queued:        %8d' % queued_items
        if locator_times:
            print 'average locator time: %8.2f secs' % (float(sum(t[0] for t in locator_times)) / len(locator_times))
            #print sorted(locator_times, key=lambda t:t[0], reverse=True)[:10]
        print
        if run_time < 120:
            sleep(1)
        else:
            sleep(5)

if __name__ == '__main__':
    t_status = spawn_link_exception(status_thread)
    t_item_queue = spawn_link_exception(add_to_item_queue)
    for i in range(80):
        spawn_link_exception(run_find_item)
    #t_index_items = spawn_link_exception(index_items)
    for i in range(8):
        spawn_link_exception(run_solr_queue, i)

    #joinall([t_run_find_item, t_item_queue, t_index_items, t_solr])

    sleep(1)
    print 'join item_queue thread'
    t_item_queue.join()
    print 'item_queue thread complete'
    #print 'join item_and_host_queue:', item_and_host_queue.qsize()
    #item_and_host_queue.join()
    #print 'item_and_host_queue complete'
    for host, host_queue in host_queues.items():
        qsize = host_queue.qsize()
        print 'host:', host, qsize
        host_queue.join()

    print 'join solr_queue:', solr_queue.qsize()
    solr_queue.join()
    print 'solr_queue complete'
