from Queue import Queue
import threading, datetime, re, httplib
from collections import defaultdict
from socket import socket, AF_INET, SOCK_DGRAM, SOL_UDP, SO_BROADCAST, timeout
from urllib import urlopen
from time import sleep, time
from lxml.etree import Element, tostring
from unicodedata import normalize

def add_field(doc, name, value):
    field = Element("field", name=name)
    field.text = normalize('NFC', unicode(value))
    doc.append(field)

solr_host = 'ia331504:8983'

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

item_queue = Queue(maxsize=10000)
item_and_host_queue = Queue(maxsize=10000)
host_queues = defaultdict(lambda: Queue())
host_threads = {}
solr_queue = Queue(maxsize=10000)
counter_lock = threading.Lock()
items_processed = 0
input_counter_lock = threading.Lock()
input_count = 0
total = 1899481

re_ia_host = re.compile('^ia(\d+).us.archive.org$')
def use_secondary(host):
    m = re_ia_host.match(host)
    num = int(m.group(1))
    return host if num % 2 else 'ia%d.us.archive.org' % (num + 1)

def use_primary(host):
    m = re_ia_host.match(host)
    num = int(m.group(1))
    return host if num % 2 == 0 else 'ia%d.us.archive.org' % (num - 1)

def add_to_item_queue():
    global input_count
    print 'add_to_item_queue'
    skip = None
    for line in open('/home/edward/scans/book_data_2010-10-15'):
        input_counter_lock.acquire()
        input_count += 1
        input_counter_lock.release()
        #(ia, title, collection, imagecount, foldoutcount, scandate_dt, scancenter, size, scanner, repub_state) = eval(line)
        ia = line[:-1]
        if skip:
            if ia == skip:
                skip = None
            continue
        #collection = set(collection.split(';'))
        #if 'printdisabled' in collection or 'lendinglibrary' in collection:
        #    continue
        #if ia[0] == '(' and ia[-1] == ')':
        #    continue
        item_queue.put(ia)

re_loc = re.compile('^(ia\d+\.us\.archive\.org):(/\d+/items/(.*))$')

class FindItemError(Exception):
    pass

def find_item(ia):
    s = socket(AF_INET, SOCK_DGRAM, SOL_UDP)
    s.setblocking(1)
    s.settimeout(4.0)
    s.setsockopt(1, SO_BROADCAST, 1)
    s.sendto(ia, ('<broadcast>', 8010))
    for attempt in range(5):
        (loc, address) = s.recvfrom(1024)
        m = re_loc.match(loc)

        ia_host = m.group(1)
        ia_path = m.group(2)
        if m.group(3) == ia:
            return (ia_host, ia_path)
    raise FindItemError

def run_find_item():
    while True:
        ia = item_queue.get()
        try:
            (host, path) = find_item(ia)
        except (timeout, FindItemError):
            item_queue.task_done()
            continue
        item_and_host_queue.put((ia, host, path))
        item_queue.task_done()

def run_queues():
    live = dict((t.name, t) for t in threading.enumerate())

    for host, queue in host_queues.items():
        if host in live and live[host].is_alive():
            continue
        ia, filename = queue.pop()
        t = threading.Thread(name=host, target=read_text_from_node, args=(ia, host, filename))
        t.start()
        print >> log, ('thread started', host, ia)
        log.flush()
        if not queue:
            del host_queues[host]

nl_page_count = 'page count: '
def read_text_from_node(host):
    global items_processed
    while True:
        ia, filename = host_queues[host].get()
        url = 'http://%s/fulltext/abbyy_to_text.php?file=%s' % (host, filename)
        reply = urlopen(url).read()
        if not reply:
            host_queues[host].task_done()
            continue
        index = reply.rfind(nl_page_count)
        last_nl = reply.rfind('\n')
        assert last_nl != -1
        body = reply[:index].decode('utf-8')
        assert reply[-1] == '\n'
        page_count = reply[index+len(nl_page_count):-1]
        if not page_count.isdigit():
            print url
        assert page_count.isdigit()
        solr_queue.put((ia, body, page_count))
        counter_lock.acquire()
        items_processed += 1
        counter_lock.release()
        host_queues[host].task_done()

re_href = re.compile('href="([^"]+)"')

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


def index_items():
    while True:
        (ia, host, path) = item_and_host_queue.get()
        host = use_secondary(host)
        if not host:
            item_and_host_queue.task_done()
            continue
        filename = ia + '_abbyy'
        filename_gz = filename + '.gz'

        try:
            dir_html = urlopen('http://%s/%s' % (host, path)).read()
        except:
            host = use_primary(host)
            dir_html = urlopen('http://%s/%s' % (host, path)).read()
        filename = find_abbyy(dir_html, ia)
        if not filename:
            item_and_host_queue.task_done()
            continue

        host_queues[host].put((ia, path + '/' + filename))
        if host not in host_threads:
            t = threading.Thread(name=host, target=read_text_from_node, args=(host,))
            host_threads[host] = t
            t.start()
        item_and_host_queue.task_done()

def build_doc(ia, body, page_count):
    doc = Element('doc')
    add_field(doc, 'ia', ia)
    add_field(doc, 'body', body)
    add_field(doc, 'body_length', len(body))
    add_field(doc, 'page_count', page_count)
    return doc

def run_solr_queue():
    h1 = httplib.HTTPConnection(solr_host)
    h1.connect()
    while True:
        (ia, body, page_count) = solr_queue.get()
        add = Element("add")
        doc = build_doc(ia, body, page_count)
        add.append(doc)
        r = tostring(add).encode('utf-8')
        url = 'http://%s/solr/inside/update' % solr_host
        h1.request('POST', url, r, { 'Content-type': 'text/xml;charset=utf-8'})
        response = h1.getresponse()
        response_body = response.read()
        assert response.reason == 'OK'
        solr_queue.task_done()

t0 = time()

def status_thread():
    while True:
        run_time = time() - t0
        print 'run time:         %8.2f minutes' % (float(run_time) / 60)
        print 'input queue:      %8d' % item_queue.qsize()
        print 'after find_item:  %8d' % item_and_host_queue.qsize()
        print 'solr queue:       %8d' % solr_queue.qsize()

        input_counter_lock.acquire()
        rec_per_sec = float(input_count) / run_time
        remain = total - input_count
        input_counter_lock.release()

        sec_left = remain / rec_per_sec
        hours_left = float(sec_left) / (60 * 60)
        print 'input count:      %8d (%.2f items/second)' % (input_count, rec_per_sec)
        print '                  %8.2f hours left (%.1f days/left)' % (hours_left, hours_left / 24)

        counter_lock.acquire()
        print 'items processed:  %8d (%.2f items/second)' % (items_processed, float(items_processed) / run_time)
        counter_lock.release()

        host_count = 0
        queued_items = 0
        for host, host_queue in host_queues.items():
            if not host_queue.empty():
                host_count += 1
            qsize = host_queue.qsize()
            queued_items += qsize
        print 'host queues:      %8d' % host_count
        print 'items queued:     %8d' % queued_items
        print
        if run_time < 120:
            sleep(1)
        else:
            sleep(5)

t1 = threading.Thread(target=add_to_item_queue)
t1.start()
t2 = threading.Thread(target=run_find_item)
t2.start()
t3 = threading.Thread(target=index_items)
t3.start()
t_solr1 = threading.Thread(target=run_solr_queue)
t_solr1.start()
t_solr2 = threading.Thread(target=run_solr_queue)
t_solr2.start()
t5 = threading.Thread(target=status_thread)
t5.start()

item_queue.join()
item_and_host_queue.join()
for host, host_queue in host_queues.items():
    host_queue.join()
solr_queue.join()
