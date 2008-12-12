import webtest
import datetime
import os

def read_config():
    import ConfigParser, os
    config = ConfigParser.RawConfigParser()
    config.read(os.getenv('HOME') + '/.oltestrc')
    username = config.get('account', 'username')
    password  = config.get('account', 'password')
    return username, password

class AccountTest(webtest.TestCase):
    def testLogin(self, b=None):
        username, password = read_config()

        b = b or webtest.Browser()
        b.open('/account/login')
        b.select_form(name='login')
        b['username'] = username
        b['password'] = password
        b.submit()
        self.assertTrue('Log out' in b.get_text())

    def testRegister(self):
        b = webtest.Browser()
        b.open('/account/register')

    def testEdit(self):
        b = webtest.Browser()
        self.testLogin(b)
        b.follow_link(url_regex='/user/')
        b.follow_link(url_regex='m=edit')
        b.select_form(predicate=lambda f: f.action.endswith('?m=edit'))
        desc = b['description'].splitlines()
        desc = [datetime.datetime.utcnow().isoformat() + ' -- testing edit -- <br/>'] + desc[:10]
        b['description'] = "\n".join(desc)
        b['_comment'] = 'testing edits'
        b.submit()

    def testChangePassword(self):
        b = webtest.Browser()
        self.testLogin(b)
        b.follow_link(text='Preferences')
        b.follow_link(text='Change Password')
        b.select_form(index=-1)
        username, password = read_config()
        b['oldpassword'] = password
        b['password'] = password
        b['password2'] = password
        b.submit()

if not os.path.exists(os.getenv('HOME') + '/.oltestrc'):
    print '~/.oltestrc notfound, ignoring AccountTest'
    del AccountTest

if __name__ == "__main__":
    webtest.main()
