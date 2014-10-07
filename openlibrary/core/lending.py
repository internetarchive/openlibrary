"""Module for providing core functionality of lending on Open Library.
"""
import web
import urllib, urllib2
import simplejson

def is_loaned_out(identifier):
    """Returns True if the given identifier is loaned out.

    This doesn't worry about waiting lists.
    """
    return is_loaned_out_on_ol(identifier) or is_loaned_out_on_acs4(identifier) or is_loaned_out_on_ia(identifier)


def is_loaned_out_on_acs4(item_id):
    """Returns True if the item is checked out on acs4 server.
    """
    url = '%s/item/%s' % (loanstatus_url, item_id)
    try:
        d = simplejson.loads(urllib2.urlopen(url).read())
    except IOError:
        # If there is any error, assume that item is checkedout.
        # Better to deny, than giving 2 loans on the same item.
        return True
    for r in d['resources']:
        if r['loans']:
            return True

    return False


def is_loaned_out_on_ia(identifier):
    """Returns True if the item is checked out on Internet Archive.
    """
    url = "https://archive.org/services/borrow/%s?action=status" % identifier
    response = simplejson.loads(urllib2.urlopen(url).read())
    return response and response.get('checkedout')


def is_loaned_out_on_ol(identifier):
    """Returns True if the item is checked out on Open Library.
    """
    loan = get_loan(identifier)
    return bool(loan)

def get_loan(identifier):
    return web.ctx.site.store.get("loan-" + identifier)