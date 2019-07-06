import requests
from infogami import config

CIVI_SPONSOR_API = '%s/account/civi' % config.get('servername', 'http://localhost')

def get_all_sponsors():
    """
    Query civi for a list of all sponsorships, for all users.
    These results will have to be summed by user for the
    leader-board and then cached
    """
    pass  # todo, later

def get_sponsored_editions(archive_username, limit=50, offset=0):
    """
    Gets a list of books from the civi API which internet archive 
    @archive_username has sponsored
    """
    return requests.get(CIVI_SPONSOR_API).json()["works"]
    
