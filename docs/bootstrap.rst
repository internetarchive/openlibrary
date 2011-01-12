Setting up a dev instance
=========================

Setting up an Open Library dev instance requires installing third-party
software and running many services.

Supported Platforms
-------------------

The Open Library dev instance has been tested on the following platforms.

* Ubuntu 10.10
* Ubuntu 10.04

Support for Mac OS X will be available soon.

Getting the source
------------------
We use ``git`` for version control. The openlibrary code repository is
hosted on github at `git://github.com/openlibrary/openlibrary.git
<git://github.com/openlibrary/openlibrary.git>`_. You can get the
source code from there using::

    $ git clone git://github.com/openlibrary/openlibrary.git

This will create a directory called openlibrary with the entire
codebase checked out. 

If you don't have git, you can get it using::

    $ apt-get install git-core

on Ubuntu or::

    $ brew install git

on MacOS

Installing dependencies
-----------------------
The system requires a lot of 3rd party programs as well as a whole
bunch of python libraries. We have an installation script which you
can run that will setup the entire thing for you but in order to run
this script, the following packages have to be installed first. 
	
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

In addition to this, you'll need at least 1GB of RAM on your dev machine
or virtual machine.

To install all of these on Ubuntu/Debian::

    $ sudo apt-get install memcached postgresql git-core openjdk-6-jre-headless python-virtualenv python-dev libpq-dev libxslt-dev

To install all of them on Mac OS X: ::

    $ brew install postgresql git
    $ sudo easy_install virtualenv
	
After the installation is done, create an user on the postgresql server::

    $ sudo -u postgres createuser openlibrary
    [sudo] password for anand: 
    Shall the new role be a superuser? (y/n) y

The following packages are necessary for Open Library development but
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



Running the install script
--------------------------

The installation is driven by the ``conf/install.ini`` config
file. Edit it if you need customize the installation process.

Now you're ready to go. Run the setuptools ``bootstrap`` command to do
the everything.::

    $ python setup.py bootstrap

The bootstrap command creates a virtualenv, installs all necessary
python packages, installs vendor software and initializes the OL
databases. A detailed log is written to ``var/log/install.log`` and
info and errors are reported to stdout and stderr respectively.

Verify the installation
-----------------------
*TDB* (insert notes on how to run smoke tests here).
      
Using the dev instance
----------------------

Once in the installation is done, running dev instance is very simple.::

    $ python setup.py start
	
This starts all the OL services using `supervisord <http://supervisord.org/>`_.

Once the services are started, Open Library dev instance will be available at:

http://0.0.0.0:8080/

Logs of the running services will be available in ``var/log/``.


Loading sample data
-------------------

Loading sample data is not yet implemented.
