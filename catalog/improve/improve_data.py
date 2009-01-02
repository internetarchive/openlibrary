from catalog.infostore import get_site
import sys

site = get_site()

site.things({'name': sys.argv[1], 'type': '/type/author'})

