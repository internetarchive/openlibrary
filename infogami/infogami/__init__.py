import web
import config
import sys

usage = """
Infogami

list of commands:

run             start the webserver
dbupgrade       upgrade the database
help            show this
"""

_actions = []
def action(f):
    """Decorator to register an infogami action."""
    _actions.append(f)
    return f

_install_hooks = []
def install_hook(f):
    """Decorator to register install hook."""
    _install_hooks.append(f)
    return f

def find_action(name):
    for a in _actions:
        if a.__name__ == name:
            return a
        
def _setup():
    if config.db_parameters is None:
        raise Exception('infogami.config.db_parameters is not specified')

    if config.site is None:
        raise Exception('infogami.config.site is not specified')
        
    web.webapi.internalerror = config.internalerror
    web.config.db_parameters = config.db_parameters
    web.config.db_printing = config.db_printing

    from infogami.utils import delegate
    delegate._load()

@action
def startserver(*args):
    """Start webserver."""
    from infogami.utils import delegate
    sys.argv = [sys.argv[0]] + list(args)
    web.run(delegate.urls, delegate.__dict__, *config.middleware)

@action
def help(name=None):
    """Show this help."""
    
    a = name and find_action(name)

    print "Infogami Help"
    print ""

    if a:
        print "    %s\t%s" %  (a.__name__, a.__doc__)
    else:
        print "Available actions"
        for a in _actions:
            print "    %s\t%s" %  (a.__name__, a.__doc__)

@action
def install():
    """Setup everything."""
    for a in _install_hooks:
        a()

def run_action(name, args=[]):
    a = find_action(name)
    if a:
        a(*args)
    else:
        print >> sys.stderr, 'unknown command', sys.argv[1]
        help()

def run():
    _setup()
    if len(sys.argv) == 1:
        run_action("startserver")
    else:
        run_action(sys.argv[1], sys.argv[2:])
