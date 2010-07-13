#!/usr/bin/python

'''
Copyright(c)2010 Internet Archive. Software license AGPL version 3.

This script installs a development copy of Open Library.
It has been tested with a clean install of Ubuntu 10.04.

This script is re-runnable, and should be run as root.
'''

import commands
import os
import urllib
import subprocess
import time
import json

install_dir = '/home/openlibrary/openlibrary'
install_user = 'openlibrary'
assert 0 == os.getuid()


def cmd(description, command):
    print description
    print "  running " + command
    (ret, out) = commands.getstatusoutput(command)
    print out + "\n"
    assert 0 == ret

def install(package):
    cmd('installing ' + package, 'DEBIAN_FRONTEND=noninteractive apt-get --force-yes -qq install ' + package)

def easyinstall(package):
    cmd('easy-installing ' + package, 'easy_install '+package)

def getjson(url):
    f = urllib.urlopen(url)
    c = f.read()
    f.close()
    obj = json.loads(c) 
    return obj

#install instructions from http://openlibrary.org/dev/docs/setup

### Dependencies

install('postgresql')
install('git-core')
install('openjdk-6-jre')

install('python-setuptools')
cmd('installing version 0.33 of web.py','easy_install web.py==0.33')

easyinstall('Babel')
easyinstall('pyyaml')

install('python-dev') #required for psycopg2
install('libpq-dev')  #required for psycopg2
easyinstall('psycopg2')

easyinstall('simplejson')
easyinstall('python-memcached')

install('libxml2-dev') #required for lxml
install('libxslt-dev') #required for lxml
easyinstall('lxml')

easyinstall('PIL')
easyinstall('pymarc')
easyinstall('genshi')


### Source code

if not os.path.exists(install_dir):
    cmd('cloning openlibrary repo', '''sudo -u %s git clone git://github.com/openlibrary/openlibrary.git "%s"''' % (install_user, install_dir))
else:
    #directory already exists, so this script is being re-run
    cmd('updating source', '''cd "%s" && sudo -u %s git pull''' % (install_dir, install_user))
 
cmd('run setup.sh to checkout other source code', '''cd "%s" && sudo -u %s ./setup.sh''' % (install_dir, install_user))


### Open Library Web Server

print 'creating postgres user %s and not checking for errors' % install_user
#this command will return an error if the user already exists, just ignore it
commands.getstatusoutput('''sudo -u postgres createuser -d -S -R %s''' % install_user)

print 'creating openlibrary db and not checking for errors\n'
#this command will return an error if the db already exists...
commands.getstatusoutput('''sudo -u %s createdb openlibrary''' % install_user)


cmd('copying configuration file', '''cat %s/conf/sample_openlibrary.yml |perl -p -e 's/anand/%s/g;' > %s/openlibrary.yml''' % (install_dir, install_user, install_dir))

cmd('bootstapping', '''cd %s && sudo -u %s ./scripts/openlibrary-server openlibrary.yml install''' % (install_dir, install_user))



#start up an instance of OL on the default port, so we can create users
print 'Starting up an OL instance!'

p = subprocess.Popen('''cd %s && sudo -u %s ./scripts/openlibrary-server openlibrary.yml''' % (install_dir, install_user), shell=True)


print "Waiting 5 seconds for OL to start up..."
time.sleep(5)
print "done waiting for OL to start"

#check to see if user openlibrary already exists
obj = getjson('http://0.0.0.0:8080/people/openlibrary.json')

if 'error' in obj:
    print "user openlibrary does not exist. creating it!"

    post_data = '&'.join(('displayname=openlibrary',
                            'username=openlibrary',
                            'password=openlibrary',
                            'email=' + urllib.quote('openlibrary@example.com'),
                            'agreement=yes',
                            'submit=Sign+Up'
                            ))
    
    f = urllib.urlopen('http://0.0.0.0:8080/account/create', post_data)
    c = f.read()
    f.close()

    #print "received this response:"
    #print c

    time.sleep(2) #wait for things to settle

    print "verifying the openlibrary account was created"
    obj = getjson('http://0.0.0.0:8080/people/openlibrary.json')
    assert "error" not in obj

#check to see if openlibrary user is in admin group
obj = getjson('http://0.0.0.0:8080/usergroup/admin.json')
isAdmin = False
for user in obj['members']:
    if '/people/openlibrary' == user['key']:
        isAdmin = True

if not isAdmin:
    post_data = 'type.key=%2Ftype%2Fusergroup&description=Group+of+admin+users.&members%230=%2Fpeople%2Fadmin&members%231=%2Fpeople%2Fopenlibrary&members%232=&members%233=&members%234=&members%235=&members%236=&members%237=&_comment=&_save=Save'

    f = urllib.urlopen('http://0.0.0.0:8080/usergroup/admin?m=edit', post_data)
    c = f.read()
    f.close()
    time.sleep(2)

    #verify openlibrary user is now in admin group
    print 'verifying openlibrary user was added to admin group'
    obj = getjson('http://0.0.0.0:8080/usergroup/admin.json')
    isAdmin = False
    for user in obj['members']:
        if '/people/openlibrary' == user['key']:
            isAdmin = True
    assert isAdmin

else:
    print "openlibrary user is already an admin"


#add openlibrary user to api usergroup, if needed
in_api_group = False
obj = getjson('http://0.0.0.0:8080/usergroup/api.json')
if 'members' in obj:
    for user in obj['members']:
        if '/people/openlibrary' == user['key']:
            in_api_group = True

if not in_api_group:
    post_data = 'type.key=%2Ftype%2Fusergroup&description=&members%230=%2Fpeople%2Fopenlibrary&members%231=&members%232=&members%233=&members%234=&_comment=&_save=Save'

    f = urllib.urlopen('http://0.0.0.0:8080/usergroup/api?m=edit', post_data)
    c = f.read()
    f.close()
    time.sleep(2)

    #verify openlibrary user is now in api group
    print 'verifying openlibrary user was added to api group'
    obj = getjson('http://0.0.0.0:8080/usergroup/api.json')
    in_api_group = False
    for user in obj['members']:
        if '/people/openlibrary' == user['key']:
            in_api_group = True
    assert in_api_group
else:
    print "/people/openlibrary already in api group"

print "restarting server!"
p.terminate()
