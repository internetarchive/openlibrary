Dev Instance
============

Installing Dependencies
------------------------

Installing CouchDB
^^^^^^^^^^^^^^^^^^

On Linux, installing CouchDB involves installing so many dependencies, some of
them are incompatible with Ubuntu/Debian installations. Fortunately, a binary
distribution with all the binaries is provided by Couchbase.

http://www.couchbase.com/download

The problem with that distribution is that it is interactive and it won't be
possible to automate the installation. To overcome this problem, the
binaries after running the interactive installation are taken and bundled. The
OL install script downloads the bundle, unpacks it and runs a script to
update the path in some scripts and config files.

The created bundle ``couchdb-1.0.1-linux-binaries.tgz`` is uploaded to
http://www.archive.org/details/ol_vendor.

On Max OS X, installing CouchDB is somewhat easier than installing on Linux.
However, to make the installations on both Mac and Linux similar, binaries are taken from
`CouchDBX`_ app.

Unlike Linux, where ``bin`` and ``etc`` are available in the top-level, Mac
binaries have them at two levels deep. To make both distributions identical, a
``bin/couchdb`` script is added and ``etc`` is symlinked from
``couchdb_1.0.1/etc``. Also, the Mac CouchDB script expects the base directory
should be the working directory. The above ``bin/couchdb`` script, takes of
this too.

.. _CouchDBX: http://dl.couchone.com/dl/26f246a0fe23d6a53d532671330bf06d/CouchDBX-1.0.1.1.zip
