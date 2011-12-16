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
		   
Apache Solr (installed by the installation script)		   
	The search engine.

On Linux, you will also have to install the following dev packages
``python-dev``, ``libpq-dev`` and ``libxslt-dev``.


Some `Python packages`_ are also required, but they will be automatically installed by the installation script.

.. _Python packages: https://github.com/internetarchive/openlibrary/tree/master/requirements.txt