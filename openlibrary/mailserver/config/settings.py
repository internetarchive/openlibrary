# This file contains python variables that configure Lamson for email processing.
import yaml
import couchdb
import logging

from openlibrary.core import support

# You may add additional parameters such as `username' and `password' if your
# relay server requires authentication, `starttls' (boolean) or `ssl' (boolean)
# for secure connections.
# relay_config = {'host': 'localhost', 'port': 8825}
relay_config = {'host': 'localhost', 'port': 25}

receiver_config = {'host': 'localhost', 'port': 8823}

handlers = ['app.handlers.cases']

router_defaults = {'host': '.+'}

template_config = {'dir': 'app', 'module': 'templates'}

# Ready the support infrastructure
try:
    cfg = yaml.load(open("/home/noufal/github/nibrahim/openlibrary/conf/openlibrary.yml"))
    db = couchdb.Database(cfg['admin']['admin_db'])
    support_db = support.Support(db)
    logging.info("Initialised connection to support database")
except Exception:
    logging.critical("Couldn't initialise support database. Bailing out!", exc_info = True)
    raise


# the config/boot.py will turn these values into variables set in settings


