"""
TDB Logger.

Log format:

    log     = item*
    item    = key " " id "\n" fields "\n"
    fields  = field*
    key     = "thing" 
            | "version"
        
    field   = name ": " value "\n"
    name    = <string with tab, newline and : escaped>
    value   = none
            | integer
            | utf8_string
            | reference
            | list
    
    none    = "None"
    integer = digit+
    utf8_string = <"> utf8_char* <">
    reference = t integer
    list = "[" + values + "]"
    values = empty
            | value ("," value)*
    digit = [0-9]
"""

import threading
import os
import re

logfile = None

# log msg for one transaction is stored in this file and on commit,
# this file's content is appended to the logfile and this file is removed.
txfilename = "transaction.log"
txfile = None

lock = threading.RLock()

def set_logfile(f):
    global logfile
    logfile = f
    
def transact():
    if logfile:
        _acquire()
    
def commit():
    if logfile:
        f = open(txfilename)
        msg = f.read()
        f.close()
        logfile.write(msg)
        logfile.flush()
        os.fsync(logfile.fileno())
        _release()

def rollback():
    if logfile:
        _release()

def log(_name, id, **kw):
    """Logs one item."""
    if logfile:
        msg = format(_name, id, kw)
        txfile.write(msg)
        txfile.flush()
        os.fsync(txfile.fileno())

def _acquire():
    """Acquires the lock and creates transaction log file."""
    global txfile
    lock.acquire()
    txfile = open(txfilename, 'w')

def _release():
    """Deletes the transaction log file and releases the lock."""
    global txfile
    txfile.close()
    txfile = None
    os.remove(txfilename)
    lock.release()
        
def is_consistent():
    """Checks if the log file is consistent state."""
    return os.path.exists(txfilename) is False

def format(_name, id, kw):
    s = ""
    s += "%s %d\n" % (_name, id)
    for k, v in kw.iteritems():
        s += "%s: %s\n" % (_keyencode(k), _encode(v))
    s += '\n'
    return s

def _keyencode(key):
    key = key.replace('\\', r'\\')
    key = key.replace('\n', r'\n')
    key = key.replace('\t', r'\t')
    key = key.replace(':', r'\:')
    return key
    
def _keydecode(key):
    rx = re.compile(r"\\([\\nt:])")
    env = {
        '\\': '\\', 
        'n': '\n', 
        't': '\t', 
        ':': ':'
    }
    return rx.sub(lambda m: env[m.group(1)], key)

def xrepr(s): return "'" + repr('"' + s)[2:]

def _encode(value):
    from tdb import Thing

    if isinstance(value, list):
        return '[%s]' % ", ".join([_encode(v) for v in value])
    elif isinstance(value, str):
        return xrepr(value)
    elif isinstance(value, unicode):
        return xrepr(value.encode('utf-8'))
    elif isinstance(value, (int, long)):
        return repr(int(value))
    elif isinstance(value, Thing):
        return 't' + _encode(value.id)
    else:
        return repr(value)

def parse(filename, infinite=False):
    fd = open(filename)
    return parse1(fd, infinite)

def parse1(fd, infinite=False):
    """Parses a tdb log file and returns an iteratable over the contents.
    If argument 'infinite' is true, the iterable never terminates.
    It instead expects the file to keep growing as new log records
    arrive, so on reaching end of file it blocks until more data
    becomes available.   If 'infinite' is false, generator terminates
    when it reaches end of log file.
    """
    from tdb import LazyThing

    if not infinite and fd.tell() != 0:
        raise NotImplementedError, "can't seek in non-tailing logfile"

    def parse_items():
        """Parses the file and returns an iteratable over the items."""
        lines = []

        def infinite_lines(fd):
            # generate a sequence of the lines in fd, never
            # terminating.  On reaching end of fd, fd.read(1)
            # will block until more characters are available.
            while True:
                yield ''.join(iter(lambda: fd.read(1), '\n'))

        if infinite:
            xlines = infinite_lines(fd)
        else:
            xlines = (x.strip() for x in fd.xreadlines())
        
        for line in xlines:
            if line == "":
                yield lines
                lines = []
            else:
                lines.append(line)

    class LazyThing(LazyThing):
        def __repr__(self):
            return 't' + str(self.id)

    class env(dict):
        def __getitem__(self, name):
            """Returns LazyThing(xx) for key txx"""
            if name.startswith('t'):
                return LazyThing(int(name[1:]))
            else:
                raise KeyError, name

    # dirty hack to decode the value using eval
    def decode(value):
        return eval(value, env())
                        
    def parse_data(lines):
        """Parses each line containing name-value pair and 
        returns the result as a dictionary."""
        d = {}
        for line in lines:
            name, value = line.split(":", 1)
            name = _keydecode(name)
            d[name] = decode(value)
        return d
        
    for item in parse_items():
        key, id = item[0].split()
        data = parse_data(item[1:])
        yield key, id, data

def parse2(p1):
    from tdb import Thing, LazyThing

    while 1:
        thing = p1.next()
        version = p1.next()
        data = p1.next()

        yield Thing(thing[1], thing[2]['name'],
                    LazyThing(thing[2]['parent_id']),
                    data[2].pop('__type__'), data[2])
        
def parse2a(p1):
    """Generate sequence of things retrieved from tdb, given a parsed logfile
    stream (from logger.parse) as input"""
    from tdb import withID
    
    while 1:
        x = p1.next()
        if x[0] != 'version': continue
        yield withID(x[2]['thing_id'])

def parse2b(p1):
    from tdb import Thing, LazyThing, withID
    
    while 1:
        x = p1.next()
        
        if x[0] == 'thing':
            thing = x
            version = p1.next()
            data = p1.next()
            
            yield Thing(thing[1], thing[2]['name'],
                        LazyThing(thing[2]['parent_id']),
                        data[2].pop('__type__'), data[2])
        elif x[0] == 'version':
            yield withID(x[2]['thing_id'])
        else:
            raise ValueError, "I wasn't expecting that..."

def load(filename):
    """Loads a tdb log file into database."""
    def savedatum(vid, key, value, ordering=None):
        # since only one level lists are supported, 
        # list type can not have ordering specified.
        if isinstance(value, list) and ordering is None:
            for n, item in enumerate(v):
                savedatum(vid, k, item, n)
            return
        elif isinstance(value, str):
            dt = 0
        elif isinstance(value, Thing):
            dt = 1
            value = value.id
        elif isinstance(value, (int, long)):
            dt = 2
        elif isinstance(value, float):
            dt = 3
        else:
            raise BadData, value
        web.insert('datum', False, 
          version_id=vid, key=key, value=value, data_type=dt, ordering=ordering)

    import web
    # assumes web.load is already called
    web.transact()
    for key, id, data in parse(filename):
        if key == 'thing':
            web.insert('thing', id=id, **data)
        elif key == 'version':
            web.insert('version', id=id, **data)
        elif key == 'data':
            vid = id
            for k, v in data.items():
                if isinstance(v, list):
                    for n, item in enumerate(v):
                        savedatum(vid, k, item, n)
                else:
                    savedatum(vid, k, v)
    web.commit()

if __name__ == "__main__":
    import sys
    for key, id, data in parse(sys.argv[1]):
        print key, id, data
