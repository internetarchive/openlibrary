#! /bin/bash
# 
# Script to install dependencies for setting up dev instance
#

function install_linux_dependencies() {
    echo "installing dependencies"
    sudo apt-get -y install memcached postgresql git-core openjdk-6-jre-headless python-virtualenv python-dev libpq-dev libxslt-dev
    
    echo "creating postgres user"
    sudo -u postgres createuser -s $USER
}

function install_macosx_dependencies() {
    echo "this is not yet implemented"
}

uname=$(uname)

if [ "$uname" == "Darwin" ]
then
    install_macosx_dependencies()
else
    install_linux_dependencies()
fi