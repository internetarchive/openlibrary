#! /bin/bash
# 
# Script to install dependencies for setting up dev instance
#

function log() {
    echo -- $*
}

function install_linux_dependencies() {
    echo "installing dependencies"
    
    packages="memcached postgresql git-core openjdk-6-jre-headless python-virtualenv python-dev libpq-dev libxslt-dev "
    # additional packages required for installing PIL
    packages="$packages  zlib1g-dev libfreetype6-dev libjpeg62-dev liblcms1-dev"
    
    sudo apt-get -y install $packages
    
    echo "creating postgres user"
    sudo -u postgres createuser -s $USER
}

function install_macosx_dependencies() {
    if ! brew --version > /dev/null 2>&1
    then
        log "installing homebrew"
        curl -fsSLk https://gist.github.com/raw/323731/install_homebrew.rb | ruby
    else
        log "homebrew installation found."
    fi
    
    log "installing wget"
    brew install wget
    
    log "installing python setuptools"
    wget -q http://peak.telecommunity.com/dist/ez_setup.py -O /tmp/ez_setup.py
    sudo python ez_setup.py -U setuptools
    
    log "installing virtualenv"
    sudo easy_install virtualenv
}

uname=$(uname)

if [ "$uname" == "Darwin" ]
then
    install_macosx_dependencies
else
    install_linux_dependencies
fi
