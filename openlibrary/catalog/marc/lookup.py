import web
import dbhash

dbm = dbhash.open("/2/pharos/imagepdfs/oclc_to_marc.dbm", "r")

urls = (
    '/', 'index'
)

class index:
    def GET(self):
        web.header('Content-Type','text/html; charset=utf-8', unique=True)

        input = web.input()
        if 'oclc' in input:
            html_oclc = web.htmlquote(input.oclc)
            print "<html>\n<head><title>OCLC to MARC: %s</title><body>" % html_oclc
        else:
            print "<html>\n<head><title>OCLC to MARC</title><body>"
        print '<form method="get">'
        print 'OCLC:'
        if 'oclc' in input:
            print '<input type="text" name="oclc" value="%s">' % html_oclc
        else:
            print '<input type="text" name="oclc">'
        print '<input type="submit" value="Find MARC">'
        print '</form>'

        if 'oclc' in input:
            print 'Searching for OCLC: %s<p>' % html_oclc
            if input.oclc in dbm:
                loc = dbm[input.oclc]
                print '<ul>'
                for l in loc.split(' '):
                    print '<li><a href="http://openlibrary.org/show-marc/%s">%s</a>' % (l, l)
                print '</ul>'
            else:
                print html_oclc, 'not found'

web.webapi.internalerror = web.debugerror

if __name__ == '__main__':
    web.run(urls, globals(), web.reloader)
