setup.py commands
=================

Most openlibrary operations are modeled as setup.py commands.

bootstrap
---------

Bootstraps the dev instance. 

::

    $ python setup.py bootstrap
    
Bootstrap command is explained in :doc:`bootstrap`.

start
-----

Starts all the OL services.::

    $ python setup.py start
    
This command starts supervisord using configuration from ``conf/supervisor/linux.ini`` or ``conf/supervisor/macosx.ini`` based on the platform.
    
Logs of the services are written to :file:`var/log`.

shell
-----

Start a bash shell with the env required for running all OL scripts. ::

    $ python setup.py shell

This starts a bash shell with `conf/bashrc`_ as rc file.

.. _conf/bashrc: http://github.com/internetarchive/openlibrary/blob/master/conf/bashrc

test
----

Runs all the test cases. 

::

    $ python setup.py test

Behind the scenes it runs :file:`scripts/runtests.sh`.

build_sphinx
------------

Builds the sphinx docs. 

::

    $ python setup.py build_sphinx
    
The docs will be generated in ``build/sphinx/html/``.

----

The custom setup.py commands are implemented in `setup_commands.py`_.

.. _setup_commands.py: http://github.com/internetarchive/openlibrary/tree/master/openlibary/core/setup_commands.py

To know more about how to add custom setuptools commands, see:

http://tarekziade.wordpress.com/2007/09/30/extending-setuptools-adding-a-new-command/



