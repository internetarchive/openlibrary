import os

def pytest_funcarg__dummy_crontabfile(request):
    "Creates a dummy crontab file that can be used for to try things"
    cronfile = os.tmpnam()
    ip = """* * * * * cmd1
* * * * * cmd2"""
    f = open(cronfile,"w")
    f.write(ip)
    f.close()
    request.addfinalizer(lambda : os.remove(cronfile))
    return cronfile
    
def pytest_funcarg__crontabfile(request):
    """Creates a file with an actual command that we can use to test
    running of cron lines"""
    if os.path.exists("/tmp/crontest"):
        os.unlink("/tmp/crontest")
    cronfile = os.tmpnam()
    ip = "* * * * * touch /tmp/crontest"
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

