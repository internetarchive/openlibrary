BROKER_HOST = "localhost"
BROKER_PORT = 5672
# BROKER_USER = "myuser"
# BROKER_PASSWORD = "mypassword"
# BROKER_VHOST = "myvhost"

# CELERY_RESULT_BACKEND = "database"
# CELERY_RESULT_DBURI = "postgresql:///openlibrary"
CELERY_RESULT_BACKEND = "couchdb"
CELERY_RESULT_DBURI = "http://localhost:5984/celery"


CELERY_IMPORTS = ("openlibrary.tasks",)

# These two files need to be separately mentioned since the tasks will
# run in the celery workers
OL_CONFIG = "conf/openlibrary.yml"

# Repeating tasks
from datetime import timedelta

CELERYBEAT_SCHEDULE = {
    "runs-every-30-seconds": {
        "task": "openlibrary.tasks.update_support_from_email",
        "schedule": timedelta(seconds=30),
    },
}

from celery.backends import BACKEND_ALIASES
BACKEND_ALIASES['couchdb'] = "openlibrary.core.celery_couchdb.CouchDBBackend"

CELERY_ALWAYS_EAGER = True
