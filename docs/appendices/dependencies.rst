Dependencies
============

The system requires a lot of 3rd party programs as well as a whole
bunch of python libraries. We have an installation script which you
can run that will setup the entire thing for you but in order to run
this script, the following packages have to be installed first. 

Git
   For getting the source repository
	
PostgreSQL 8.2 or later (``psql``)
   This is where we store our data

Python 2.5 or later (``python``)
   The application is written in python

Java Runtime (tested with ``openjdk-6-jre``)
     	   The indexer (``solr``) is a Java application

Python virtualenv (``python-virtualenv``)
           Necessary to create "virtual" installations of Python so
           that we can install packages without touching your system
           distribution. More details at `the virtualenv PyPI
           page <http://pypi.python.org/pypi/virtualenv>`_.

memcached (``memcached``)
	  Used for distributed caching.

On Linux, you will also have to install the following dev packages
``python-dev``, ``libpq-dev`` and ``libxslt-dev``.


The following python packages are necessary for Open Library development but
they're automatically installed by the installation script. They're
not all necessary to run but for things like testing, documentation etc.

* Apache Solr
* Apache CouchDB
* CouchDB Lucene
* Python Packages:

  * argparse
  * Babel 
  * couchdb
  * genshi
  * lxml
  * PIL
  * psycopg2 
  * pymarc
  * python-memcached 
  * pyyaml 
  * simplejson 
  * web.py (version 0.33)
  * supervisor
  * py.test
  * sphinx
