BROKER_HOST = "localhost"
BROKER_PORT = 5672
# BROKER_USER = "myuser"
# BROKER_PASSWORD = "mypassword"
# BROKER_VHOST = "myvhost"

CELERY_RESULT_BACKEND = "amqp"
CELERY_IMPORTS = ("openlibrary.tasks", )

OL_CONFIG = "conf/openlibrary.yml"
