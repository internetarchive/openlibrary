"""Test the user interface using a robot."""
import webtest
import web

#web.Browser.DEBUG = True

class UITest(webtest.TestCase):
    def testHome(self):
        b = webtest.Browser()
        b.open('/')

    def testSearch(self):
        b = webtest.Browser()
        b.open('/search?q=tom+sawyer')
        
    def _testPage(self, path):
        b = webtest.Browser()
        b.open(path)

        b.follow_link(url_regex='m=edit')
        b.follow_link(url_regex='m=history')
        b.open(path + '?m=diff')
        b.open(path + '?m=change_cover')
        
    def testBook(self):
        self._testPage('/b/OL1M')

    def testAuthor(self):
        self._testPage('/a/OL1A')

    def testRecentChanges(self):
        b = webtest.Browser()
        b.open('/recentchanges')
            
if __name__ == "__main__":
    webtest.main()
