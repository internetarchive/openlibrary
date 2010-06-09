import os.path

# ~/.olrc looks like this:
# 
# db=''
# user=''
# pw= ''
# host = ''
# secret_key = ''
 
def read_rc():
    rc_file = os.path.expanduser('~/.olrc')
    if not os.path.exists(rc_file):
        return {}
    f = open(rc_file)
    return eval('dict(' + ', '.join(i for i in f if i) + ')')
