import subprocess
import web

from pygments import highlight
from pygments.lexers import DiffLexer
from pygments.formatters import HtmlFormatter

class CommandError(Exception):
    def __init__(self, status, message):
        self.status = status
        self.message = message
        msg = "Failed with status %s\n" % status + message
        Exception.__init__(self, msg)

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
        
    def system(self, cmd, input=None):
        """Executes the command returns the stdout.
        """
        print >> web.debug, "system", repr(cmd), input
        if input:
            stdin = subprocess.PIPE
        else:
            stdin = None
        p = subprocess.Popen(cmd, shell=True, stdin=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = p.communicate(input)
        status = p.wait()
        if status != 0:
            raise CommandError(status, err)
        else:
            return out
        
    def modified(self):
        def process(f):
            diff = self.diff(f)
            html = highlight(diff, DiffLexer(), HtmlFormatter(full=True, style="trac", nowrap=True))
            return web.storage(name=f, diff=diff, htmldiff=html)
        return [process(f) for f in self.status()]
        
    def commit(self, files, author, message):
        author = author.replace("'", "")
        cmd = "git commit --author '%s' -F - " % author + " ".join(files)
        return self.system(cmd, input=message)
        
    def push(self):
        return self.system("git push")