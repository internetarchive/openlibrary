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
* Mac OS X Snow Leopard (with `XCode`_ and `homebrew`_ installed)

Make sure you have at least 1GB of RAM on your dev machine or virtual machine.

.. _XCode: http://developer.apple.com/technologies/xcode.html
.. _homebrew: http://mxcl.github.com/homebrew/

Getting the source
------------------

Open Library uses ``git`` for version control and the `code repository`_ is
hosted on github.

.. _code repository: https://github.com/internetarchive/openlibrary

You can get the source code from there using::

   $ git clone git://github.com/internetarchive/openlibrary.git
   $ cd openlibrary

This will create a directory called openlibrary with the entire
codebase checked out.

In case you don't have git installed already, you can install it on Ubuntu using::

    $ sudo apt-get install git-core
    
and on Mac OS X using::

    $ brew install git

Installing dependencies
-----------------------

Open Library depends a lot of third-party programs.

To install all the dependencies::

    $ sudo python setup.py install_dependencies

Note that this is run as root.

See :doc:`appendices/dependencies` for the list of dependencies.
  
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

Updating an existing dev instance
----------------------------------

Like any other software, the dev instance keeps changing with time. 

To update an existing dev instance to latest version, run::

    $ python setup.py bootstrap --update
