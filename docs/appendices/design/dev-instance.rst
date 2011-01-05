Dev Instance
============

Installing Dependencies
------------------------

Installing CouchDB
^^^^^^^^^^^^^^^^^^

On Linux, installing CouchDB involves installing so many dependencies, some of
them are incompatible with ubuntu/debian installations. Fortunately, a binary
distribution with all the binaries is provided by CouchOne.

http://www.couchone.com/get

The problem with that distribution is that it is interactive and it won't be
possible to automate the installation of that. To overcome this problem, the
binaries after running the interactive installation are taken and bundled. The
ol install script, downloads the bundle, unpacks it and runs a script to
updates the path in some scripts and config files.

The created bundle ``couchdb-1.0.1-linux-binaries.tgz`` is uploaded to
http://www.archive.org/details/ol_vendor.

On Max OS X, installing couchdb is somewhat easier than installing on Linux.
However to make the installations on both mac and linux similar, binaries are taken from
`CouchDBX`_ app.

Unlike Linux, where ``bin`` and ``etc`` are available in the top-level, mac
binaries have them at 2 level deep. To make both distributions identical, a
``bin/couchdb`` script is added and ``etc`` is symlinked from
``couchdb_1.0.1/etc``. Also the mac couchdb script expects the base directory
should be the working directory. The above ``bin/couchdb`` script, takes of
this too.

.. _CouchDBX: http://dl.couchone.com/dl/26f246a0fe23d6a53d532671330bf06d/CouchDBX-1.0.1.1.zip
