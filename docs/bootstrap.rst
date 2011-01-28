.. _bootstrap:

Setting up a dev instance
=========================

Setting up an Open Library dev instance requires installing third-party
software and running many services.

Supported Platforms
-------------------

The Open Library dev instance has been tested on the following platforms.

* Ubuntu 10.10
* Ubuntu 10.04
* Mac OS X Snow Leopard

Make sure you have at least 1GB of RAM on your dev machine or virtual machine.

Installing dependencies
-----------------------

Open Library depends a lot of third-party programs as well as a whole
bunch of python libraries. 

To install all the dependencies on Ubuntu::

    $ wget -O - http://github.com/openlibrary/openlibrary/raw/master/scripts/install_dependencies.sh | bash
    
To install all the dependencies on Mac OS X::

    $ curl http://github.com/openlibrary/openlibrary/raw/master/scripts/install_dependencies.sh | bash
    
The list of dependencies is available at :doc:`appendices/dependencies`.

Getting the source
------------------

Open Library uses ``git`` for version control and the `code repository`_ is
hosted on github.

.. _code repository: http://github.com/openlibrary/openlibrary

You can get the source code from there using::

   $ git clone git://github.com/openlibrary/openlibrary.git

This will create a directory called openlibrary with the entire
codebase checked out. 
  
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
