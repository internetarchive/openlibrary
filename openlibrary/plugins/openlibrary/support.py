from infogami.utils import delegate

class support(delegate.page):
    def GET(self):
        return "Hello"
        


def setup():
    pass
