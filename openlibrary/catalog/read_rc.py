import os.path

# ~/.olrc looks like this:
# 
# db=''
# user=''
# pw= ''
# host = ''
# secret_key = ''
 
def read_rc():
    f = open(os.path.expanduser('~/.olrc'))
    return eval('dict(' + ', '.join(i for i in f if i) + ')')
