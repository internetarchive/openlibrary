"""Spam control using akismet api.
"""
import socket

# akismet module changes socket default timeout. 
# Undoing it as it might effect other parts of the system.
timeout = socket.getdefaulttimeout()

from akismet import Akismet
socket.setdefaulttimeout(timeout)
import web

from infogami import config
from infogami.infobase import client

blog_url = 'http://' + config.site
key = config.akismet_api_key

if hasattr(config, 'akismet_baseurl'):
    Akismet.antispam_baseurl = config.antispam_baseurl

spamlog = getattr(config, "akismet_log", None)

api = Akismet(key=key, blog_url=blog_url, agent='OpenLibrary')

class hooks(client.hook):
    def before_register(self, d):
        data = {}
        data['comment_type'] = "registration"
        data['comment_author'] = d['displayname']
        data['comment_author_email'] = d['email']
        comment = ""
        self.checkspam(comment, data)

    def before_new_version(self, page):
        if page.type.key == '/type/user':
            comment = page['description']
            data = {}
            data['comment_author'] = page['displayname']
            if page.website:
                data['comment_author_url'] = page.website[0]
            self.checkspam(comment, data)
    
    def checkspam(self, comment, data):
        data['user_ip'] = web.ctx.get('ip', '127.0.0.1')

        data['user_agent'] = web.ctx.env.get('HTTP_USER_AGENT', 'Mozilla/5.0')
        data['referrer'] = web.ctx.env.get('HTTP_REFERER', 'unknown')
        data['SERVER_ADDR'] = web.ctx.env.get('SERVER_ADDR', '')
        data['SERVER_ADMIN'] = web.ctx.env.get('SERVER_ADMIN', '')
        data['SERVER_NAME'] = web.ctx.env.get('SERVER_NAME', '')
        data['SERVER_PORT'] = web.ctx.env.get('SERVER_PORT', '')
        data['SERVER_SIGNATURE'] = web.ctx.env.get('SERVER_SIGNATURE', '')
        data['SERVER_SOFTWARE'] = web.ctx.env.get('SERVER_SOFTWARE', '')
        data['HTTP_ACCEPT'] = web.ctx.env.get('HTTP_ACCEPT', '')

        spam = api.comment_check(comment, data)
        if spamlog:
            f = open(spamlog, 'a')
            print >> f, spam, data
            f.close()

        if spam:
            raise Exception("The content not saved becaused it loooked like spam.")
