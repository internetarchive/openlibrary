import os

def pytest_funcarg__crontabfile(request):
    "Creates a crontab file that can be used for to try things"
    cronfile = os.tmpnam()
    ip = """* * * * * cmd1
* * * * * cmd2"""
    f = open(cronfile,"w")
    f.write(ip)
    f.close()
    request.addfinalizer(lambda : os.remove(cronfile))
    return cronfile
    
    
def pytest_funcarg__counter(request):
    """Returns a decorator that will create a 'counted' version of the
    functions. The number of times it's been called is kept in the
    .invocations attribute"""
    def counter(fn):
        def _counted(*largs, **kargs):
            _counted.invocations += 1
            fn(*largs, **kargs)
        _counted.invocations = 0
        return _counted
    return counter

