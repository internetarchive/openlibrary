#!/usr/bin/env python
"""
Fake loan status server to make dev instance work with borrowing books.
"""
import web

urls = ("/is_loaned_out/(.*)", "is_loaned_out")
app = web.application(urls, globals())


class is_loaned_out:
    def GET(self, resource_id):
        web.header("Content-type", "application/json")
        return "[]"


if __name__ == "__main__":
    app.run()
