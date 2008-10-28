import os.path

# ~/.olrc looks like this:
# 
# db=''
# user=''
# pw= ''
# host = ''
# secret_key = ''
 
def read_rc():
    return eval('dict(' + ', '.join(open(os.path.expanduser('~/.olrc'))) + ')')
