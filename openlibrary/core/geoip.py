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

gi = GeoIP.open('/usr/local/maxmind-geoip/GeoLiteCity.dat', GeoIP.GEOIP_MEMORY_CACHE)
