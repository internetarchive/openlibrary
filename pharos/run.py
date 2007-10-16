#!/usr/local/bin/python2.5
import sys, os
import web
import infogami
import infogami.config
import infogami.tdb.tdb
olderror = infogami.config.internalerror
def send(fr, to, message):
   assert not fr.startswith('-') and not to.startswith('-'), 'security'
   print >> web.debug, 'e'
   i, o = os.popen2(["/usr/sbin/sendmail", '-f', fr, to])
   i.write(message)
   i.close()
   o.close()
   del i, o

def error():
   print >> web.debug, 't'
   olderror()
   print >> web.debug, 't2'
   import sys, traceback
   tb = sys.exc_info()
   text = """From: the bugman <bugs@openlibrary.org>
To: the bugfixer <ol.errors@gmail.com>
Subject: bug: %s: %s (%s)
Content-Type: multipart/mixed; boundary="----here----"

------here----
Content-Type: text/plain
Content-Disposition: inline

%s

%s

------here----
Content-Type: text/html; name="bug.html"
Content-Disposition: attachment; filename="bug.html"

""" % (tb[0], tb[1], web.ctx.path, web.ctx.method+' '+web.ctx.home+web.ctx.fullpath, ''.join(traceback.format_exception(*tb)))
   text += str(web.djangoerror())
   send('bugs@openlibrary.org', 'ol.errors@gmail.com', text)

infogami.config.internalerror = error

#web.db._hasPooling = False
infogami.config.db_parameters = dict(dbn='postgres', host='pharosdb', db="pharos_staging", user='anand', pw='')
infogami.config.site = 'openlibrary.org'
infogami.config.cache_templates = True
infogami.config.db_printing = False
infogami.config.plugin_path += ['plugins']
infogami.config.plugins += ['openlibrary', 'search', 'pages', 'heartbeat', 'upload', 'dump', 'bookrev']
infogami.config.solr_server_address = ('pharosdb.us.archive.org', 8993)

infogami.tdb.logger.set_logfile(open("tdb.log", "a"))

infogami.config.from_address = "noreply@demo.openlibrary.org"
infogami.config.smtp_server = "mail.archive.org"

@infogami.action
def migrateusers():
    import passwd
    passwd.migrate()

if __name__ == "__main__":
    infogami.run()
