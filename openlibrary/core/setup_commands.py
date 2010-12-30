"""Distutils commands for Open Library.
"""
from setuptools import Command
import os

class StartCommand(Command):
    """Distutils command to start OL services.
    
    This is invoked by calling::
    
        python setup.py start
    """
    description = "Start Open Library services"
    user_options = []
    
    def initialize_options(self):
        """init options"""
        pass

    def finalize_options(self):
        """finalize options"""
        pass

    def run(self):
        """runner"""
        args = "supervisord -c conf/services.ini -n".split()
        os.execvp(args[0], args)

from sphinx.setup_command import BuildDoc as _BuildDoc

class BuildDoc(_BuildDoc):
    """Distutils command to build generate API docs and Sphinx documentation.
    
    This is invoked by calling::
    
        python setup.py build_sphinx     
    """
    def run(self):
        print "generating API docs..."
        os.system("python scripts/generate-api-docs.py")
        _BuildDoc.run(self)