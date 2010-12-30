Setting up a dev instance
=========================

Setting up OL dev instance requires installing third-party software, running many services. 

Supported Platforms
-------------------

Open Library dev instance works on::

* Ubuntu 10.04
* Ununtu 10.10
* Mac OS X Snow Leopard

Dependencies
------------

* PostgreSQL 8.2 or later (psql)
* Python 2.5 or later (python)
* Git (git)
* Java Runtime (tested with openjdk-6-jre)
* At least 1GB of RAM on your dev machine or virtual machine
* Python virtualenv

To install them on Ubuntu/Debian::

	$ sudo apt-get install postgresql libpq-dev git-core openjdk-6-jre-headless python-virtualenv python-dev
	$ sudo apt-get install libxslt1-dev

To install them on Mac OS X: ::

	$ brew install postgresql git
	$ sudo easy_install virtualenv
	
Make sure you create a postgres user account for you.::

	$ sudo -u postgres createuser anand
	[sudo] password for anand: 
	Shall the new role be a superuser? (y/n) y

Open Library depends also on the following packages, but they are installed by the install script.

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
  * web.py==0.33

Installation
------------

The installation is driven by install config file ``conf/install.ini``. Edit that file if you need customize installation.

The installation script is part of the Open Library repository. You need to get the repository to run the script. ::

    $ git clone git://github.com/openlibrary/openlibrary.git
    $ cd openlibrary

Now run the ``bootstrap`` command to do the remaining setup.::

	$ python setup.py bootstrap

The bootstrap command creates a virtualenv, installs all dependent python
packages, installs vendor software and initializes OL databases. Detailed log
is written to ``var/log/install.log`` and errors and info are reported to
stdout and stderr.

Run
---

Once in the installation is done, running dev instance is very simple.::

	$ python setup.py start
	...
	
This starts all the OL services using supervisord.

Once the services are started, Open Library dev instance will be available at::

	http://0.0.0.0:8080/

Sample Data
-----------

Loading sample data is not yet implemented.