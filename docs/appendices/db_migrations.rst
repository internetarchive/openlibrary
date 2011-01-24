Database Migrations
===================

Ocationally, new tables get added to openlibrary database and some existing
tables get altered. Scripts are provided to migrate the existing dev instances
to new schema.

To migrate an existing dev instance::

    $ python setup.py shell
    $ python scripts/migrate_db.py

This will look the current database schema and identifies its version and
upgrades it to the latest version.
