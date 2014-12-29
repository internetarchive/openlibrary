.. _bootstrap:

Setting up a dev instance
=========================

Open Library supports dev instance based on `Vagrant`_. This document will step you though the 
installation process.

.. _Vagrant: http://vagrantup.com/

The vagrant setup uses Ubuntu 14.04 LTS operating system. Make sure you have at least 1GB of RAM in the virtual machine.

Getting the source
------------------

Open Library uses ``git`` for version control and the `code repository`_ is
hosted on github.

.. _code repository: https://github.com/internetarchive/openlibrary

You can get the source code from there using::

   $ git clone git://github.com/internetarchive/openlibrary.git
   $ cd openlibrary

In case you don't have git installed already, you can install it on Ubuntu using::

    $ sudo apt-get install git-core
    
and on Mac OS X using::

    $ brew install git

Starting the dev-instance
-------------------------

The Open Library dev-instance can be started using::

	$ vagrant up

This will setup a virtual machine with Ubuntu 14.04, installs all dependencies, setup database and loads sample data.

Once, the virtual machine is up, you'll be able to access the website at:

http://0.0.0.0:8080/

An admin user with the following credentials is created as part of the installation.

::

  username: openlibrary
  password: openlibrary

Known Issues
------------

It is known that the following issues exist:

* Stats on the home page is not working
* /admin is failing
* subject search is not working
