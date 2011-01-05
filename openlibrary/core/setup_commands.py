"""Distutils commands for Open Library.
"""
from setuptools import Command
import os
import ConfigParser
from setuptools.command.test import test as _test

class BaseCommand(Command):
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

    def exec_command(self, args):
        env = dict(os.environ)
        virtualenv = self.get_virtualenv()
        env['PATH'] = virtualenv + "/bin:" + env['PATH']        
        os.execvpe(args[0], args, env)
    
    
class StartCommand(BaseCommand):
    """Distutils command to start OL services.
    
    This is invoked by calling::
    
        $ python setup.py start
    """
    description = "Start Open Library services"
        
    def run(self):
        """runner"""
        args = "supervisord -c conf/services.ini -n".split()
        self.exec_command(args)


class ShellCommand(BaseCommand):
    """Distutils command to start a bash shell with OL environment.
    
    This is invoked by calling::
    
        $ python setup.py shell
    """
    description = "Start bash shell with OL environment"

    def run(self):
        args = "bash --rcfile conf/bashrc".split()
        os.execvp(args[0], args)
        

class BootstrapCommand(BaseCommand):
    """Distutils command to bootstrap OL dev instance.
    
    This is invoked by calling::
    
        $ python setup.py bootstrap
    """
    description = "Bootstrap OL dev instance"
    
    def run(self):
        os.system("python scripts/setup_dev_instance.py")

class TestCommand(BaseCommand):
    """Distutils command to tun all the tests.

    This is invoked by calling::
    
        $ python setup.py test    
    """
    description = "Run all tests"
    user_options = []
    
    def run(self):
        args = "bash scripts/runtests.sh".split()
        self.exec_command(args)
        

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
    'test': TestCommand
}