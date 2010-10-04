import web, os
from StringIO import StringIO

arc_dir = '/2/edward/amazon/arc'
urls = (
    '/', 'index',
    '/(\d+\.arc)', 'arc_view',
    '/(\d+\.arc)/(\d+)', 'page_view',
)
app = web.application(urls, globals(), autoreload=True)

class arc_view:
    def GET(self, filename):
        ret = '<html><body>'
        ret += '<a href="/">back to index</a><br>'
        ret += '<h1>%s</h1>' % filename
        idx = open(arc_dir + '/' + filename + '.idx')
        arc = open(arc_dir + '/' + filename)
        for pos in idx:
            arc.seek(int(pos))
            line = arc.readline()[:-1].split(' ')
            ret += '<a href="%s/%d">from ARC</a> OR <a href="%s">original</a> %s <br>' % (filename, int(pos), line[0], line[0])
        idx.close()

        ret += '</body></html>'
        return ret

class page_view:
    def GET(self, filename, offset):
        arc = open(arc_dir + '/' + filename)
        arc.seek(int(offset))
        size = int(arc.readline().split(' ')[4])
        f = StringIO(arc.read(size))
        f.readline()
        ret = ''
        while True:
            line=f.readline()
            if line == '\r\n':
                break
        while True:
            line = f.readline()
            chunk_size = int(line, 16)
            if chunk_size == 0:
                break
            buf = f.read(chunk_size)
            ret += buf
            f.readline()
        return ret

class index:        
    def GET(self):
        ret = '<html><body><ul>'
        for filename in os.listdir(arc_dir):
            if not filename.endswith('.arc'):
                continue
            f = open(arc_dir + '/' + filename)
            line = f.readline()
            f.close()
            ret += '<li><a href="/%s">%s</a> - %s' % (filename, filename, line)
        ret += '</body></html>'
        return ret

if __name__ == "__main__":
    app.run()
