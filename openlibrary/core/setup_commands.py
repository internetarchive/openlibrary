"""Distutils commands for Open Library.
"""
from setuptools import Command
import os

class StartCommand(Command):
    """Distutils command to start OL services.
    
    This is invoked by calling::
    
        $ python setup.py start
    """
    description = "Start Open Library services"
    user_options = []
    
    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        """runner"""
        args = "supervisord -c conf/services.ini -n".split()
        os.execvp(args[0], args)
        
class BootstrapCommand(Command):
    """Distutils command to bootstrap OL dev instance.
    
    This is invoked by calling:
    
        $ python setup.py bootstrap
    """
    description = "Bootstrap OL dev instance"
    user_options = []
    
    def initialize_options(self):
        pass

    def finalize_options(self):
        pass
    
    def run(self):
        os.system("python scripts/setup_dev_instance.py")

try:
    from sphinx.setup_command import BuildDoc as _BuildDoc
except ImportError:
    _BuildDoc = object

class BuildDoc(_BuildDoc):
    """Distutils command to build generate API docs and Sphinx documentation.
    
    This is invoked by calling::
    
        $ python setup.py build_sphinx     
    """
    def run(self):
        if _BuildDoc is object:
            raise ImportError("sphinx")
        print "generating API docs..."
        #os.system("python scripts/generate-api-docs.py")
        _BuildDoc.run(self)
        
commands = {
    'bootstrap': BootstrapCommand,
    'start': StartCommand,
    'build_sphinx': BuildDoc,
}