"""Distutils commands for Open Library.
"""
from setuptools import Command
import os
import ConfigParser

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
        
    def get_virtualenv(self):
        p = ConfigParser.ConfigParser()
        p.read("conf/install.ini")
        path = p.get("install", "virtualenv")
        return os.path.expanduser(path)

    def run(self):
        """runner"""
        env = dict(os.environ)
        virtualenv = self.get_virtualenv()
        env['PATH'] = virtualenv + "/bin:" + env['PATH']
        
        args = "supervisord -c conf/services.ini -n".split()
        os.execvpe(args[0], args, env)

class ShellCommand(Command):
    """Distutils command to start a bash shell with OL environment.
    
    This is invoked by calling::
    
        $ python setup.py shell
    """
    description = "Start bash shell with OL environment"
    user_options = []
    
    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        args = ["bash", "-c", 'source conf/bashrc; bash --norc']
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
        os.system("python scripts/generate-api-docs.py")
        _BuildDoc.run(self)
        
commands = {
    'bootstrap': BootstrapCommand,
    'build_sphinx': BuildDoc,
    'shell': ShellCommand,
    'start': StartCommand,
}
