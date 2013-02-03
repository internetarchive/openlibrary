Database Migrations
===================

Occasionally, new tables get added to the openlibrary database and some existing
tables get altered. Scripts are provided to migrate the existing dev instances
to the new schema.

To migrate an existing dev instance::

    $ python setup.py shell
    $ python scripts/migrate_db.py

This will look at the current database schema, identify its version and
upgrade it to the latest version.