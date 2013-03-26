from infogami import config
import GeoIP
import web

@web.memoize
def get_db():
    try:
        geoip_db = config.get("geoip_database", '/usr/local/maxmind-geoip/GeoLiteCity.dat')
        return GeoIP.open(geoip_db, GeoIP.GEOIP_MEMORY_CACHE)
    except GeoIP.error:
        print "loading GeoIP file failed"

def get_region(ip):
    gi = get_db()
    if not gi:
        return None
    
    region = None
    try:
        record = gi.record_by_addr(ip)
        region = record['region']
    except TypeError:
        print 'geoip lookup failed for ' + ip

    return region

