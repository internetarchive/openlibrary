import os
def pytest_funcarg__crontabfile(request):
    "Creates a crontab file that can be used for to try things"
    cronfile = os.tmpnam()
    ip = """* * * * * cmd1
* * * * * cmd2"""
    f = open(cronfile,"w")
    f.write(ip)
    f.close()
    return cronfile
    
    
