Working with dev instance
=========================

Starting services
-----------------

All open library services can be started by running::

    $ python setup.py start

This command starts services using supervisord using
:file:`conf/supervisord/linux.ini` as configuration file on Linux and
:file:`conf/supervisord/macosx.ini` on Mac.

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

