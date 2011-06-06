BROKER_HOST = "localhost"
BROKER_PORT = 5672
# BROKER_USER = "myuser"
# BROKER_PASSWORD = "mypassword"
# BROKER_VHOST = "myvhost"

CELERY_RESULT_BACKEND = "database"
CELERY_RESULT_DBURI = "postgresql://@:5432/celery"

CELERY_IMPORTS = ("openlibrary.tasks", )
