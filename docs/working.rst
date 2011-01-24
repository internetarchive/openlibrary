Working with dev instance
=========================

Starting services
-----------------

All open library services can be started by running::

    $ python setup.py start

This starts all the OL services using `supervisord <http://supervisord.org/>`_.

The supervisor config files are in :file:`conf/supervisor`.

Once the services are started, Open Library dev instance will be available at:

http://0.0.0.0:8080/

Logs of the running services will be available in ``var/log/``.

Restarting services
-------------------

All the services can be restarted by stopping the supervisor using CTRL+C and starting it again.

To start individual services::

    $ python setup.py restart -s openlibrary

Look at the supervisord config files to know the list of services.

To know more about other available setup.py commands, see :doc:`appendices/setup_commands`.

Handling database schema changes
--------------------------------

See :doc:`appendices/db_migrations` to know how to upgrade database schema. 
