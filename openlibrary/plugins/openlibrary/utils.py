import urlparse
try:
    import genshi
    import genshi.filters
except ImportError:
    genshi = None
    
try:
    from BeautifulSoup import BeautifulSoup
except ImportError:
    BeautifulSoup = None
    
from infogami.utils.view import public
    
@public
def sanitize(html):
    """Remove unsafe tags and attributes from html and add rel="nofollow" attribute to all links."""
    # Can't sanitize unless genshi module is available
    if genshi is None:
        return html
        
    def get_nofollow(name, event):
        attrs = event[1][1]
        href = attrs.get('href', '')

        if href:
            # add rel=nofollow to all absolute links
            _, host, _, _, _ = urlparse.urlsplit(href)
            if host:
                return 'nofollow'
                
    try:
        html = genshi.HTML(html)
    except genshi.ParseError:
        if BeautifulSoup:
            # Bad html. Tidy it up using BeautifulSoup
            html = str(BeautifulSoup(html))
            html = genshi.HTML(html)
        else:
            raise

    stream = html | genshi.filters.HTMLSanitizer() | genshi.filters.Transformer("//a").attr("rel", get_nofollow)
    return stream.render()                                                                                   
        
