from catalog.infostore import get_site

urls = (
    '/', 'index'
)

rc = read_rc()
site = get_site()

class index:
    def GET(self):
        web.header('Content-Type','text/html; charset=utf-8', unique=True)
        key = web.input().author
        thing = site.get(key)
        print thing
        title = 'Split author'
        print "<html>\n<head>\n<title>%s</title>" % title
        print '''
<style>
th { text-align: left }
td { padding: 5px; background: #eee }
</style>'''

        print '</head><body><a name="top">'
        print thing
        print '<body><html>'


if __name__ == "__main__": web.run(urls, globals(), web.reloader)

