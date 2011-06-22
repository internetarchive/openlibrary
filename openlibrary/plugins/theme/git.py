import subprocess
import web

from pygments import highlight
from pygments.lexers import DiffLexer
from pygments.formatters import HtmlFormatter

class Git:
    """Simple interface to git.
    Expects that the working directory is the root of git repository.
    """
    def __init__(self):
        pass
    
    def add_file(self, path):
        """Adds an empty file to the repository.
        """
        pass
        
    def status(self):
        """Returns the list of modified files.
        """
        out = self.system("git status --short")
        return [line.strip().split()[-1] for line in out.splitlines() if not line.startswith("??")]
        
    def diff(self, path):
        """
        """
        return self.system("git diff " + path)
        
    def system(self, cmd):
        """Executes the command returns the stdout.
        """
        return subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE).communicate()[0]
        
    def modified(self):
        def process(f):
            diff = self.diff(f)
            html = highlight(diff, DiffLexer(), HtmlFormatter(full=True, style="trac", nowrap=True))
            return web.storage(name=f, diff=diff, htmldiff=html)
        return [process(f) for f in self.status()]