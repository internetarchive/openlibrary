import datetime

import web

def delete_old_links():
    for doc in web.ctx.site.store.values(type="account-link"):
        d = datetime.datetime.strptime(doc['created_on'], "%Y-%m-%dT%H:%M:%S.%f")
        now = datetime.datetime.utcnow()
        link_age = now - d
        key = doc['_key']
        if now - d > datetime.timedelta(days = 15):
            print "Deleting link %s with age %s"%(key, link_age)
            del web.ctx.site.store[key]
        else:
            print "Retaining link %s with age %s"%(key, link_age)

def main():
    delete_old_links()
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())

        
