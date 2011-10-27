from infogami import config
import GeoIP

def get_region(ip):
    global gi

    region = None
    try:
        record = gi.record_by_addr(ip)
        region = record['region']
    except TypeError:
        print 'geoip lookup failed for ' + ip

    return region

geoip_db = config.get("geoip_database", '/usr/local/maxmind-geoip/GeoLiteCity.dat')
gi = GeoIP.open(geoip_db, GeoIP.GEOIP_MEMORY_CACHE)
