from infogami.utils import delegate

class index(delegate.page):
    path = "/"

    def GET(self):
        return "hello, world"

class search(delegate.page):
    def GET(self):
        return "search"


