"""WSGI middleware used in Open Library.
"""
import web
import StringIO
import gzip

class GZipMiddleware:
    """WSGI middleware to gzip the response."""
    def __init__(self, app):
        self.app = app
        
    def __call__(self, environ, start_response):
        accept_encoding = environ.get("HTTP_ACCEPT_ENCODING", "")
        if not 'gzip' in accept_encoding:
            return self.app(environ, start_response)
        
        response = web.storage(compress=False)
        
        def get_response_header(name, default=None):
            for hdr, value in response.headers:
                if hdr.lower() == name.lower():
                    return value
            return default
            
        def compress(text, level=9):
            f = StringIO.StringIO()
            gz = gzip.GzipFile(None, 'wb', level, fileobj=f)
            gz.write(text)
            gz.close()
            return f.getvalue()
        
        def new_start_response(status, headers):
            response.status = status
            response.headers = headers
            
            if status.startswith("200") and get_response_header("Content-Type", "").startswith("text/"):
                headers.append(("Content-Encoding", "gzip"))
                headers.append(("Vary", "Accept-Encoding"))
                response.compress = True
            return start_response(status, headers)
        
        data = self.app(environ, new_start_response)
        if response.compress:
            return [compress("".join(data), 9)]
        else:
            return data
