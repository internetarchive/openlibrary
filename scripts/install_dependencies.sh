#! /bin/bash
# 
# Script to install dependencies for setting up dev instance
#

function log() {
    echo -- $*
}

function install_linux_dependencies() {
    echo "installing dependencies"
    
    packages="build-essential memcached postgresql git-core openjdk-6-jre-headless python-virtualenv python-dev libpq-dev libxslt-dev tzdata libgeoip-dev"
    # additional packages required for installing PIL
    packages="$packages  zlib1g-dev libfreetype6-dev libjpeg62-dev liblcms1-dev"
    # for IP address based access
    packages="$packages python-geoip"
    
    apt-get -y install $packages
    
    echo "creating postgres user $SUDO_USER"
    sudo -u postgres createuser -s $SUDO_USER
}

function install_macosx_dependencies() {
    if ! /usr/bin/which -s gcc
    then
        echo -e "\nPlease install XCode.\nhttp://developer.apple.com/technologies/xcode.html" 1>&2
        exit 3
    fi
    
    if ! /usr/bin/which -s brew
    then
        echo -e "\nPlease install Homebrew.\nhttp://mxcl.github.com/homebrew/" 1>&2
        exit 3
    fi
    
    packages="wget postgres geoip"
    for p in $packages
    do
        log "installing $p"
        sudo -u $SUDO_USER brew install $p
    done
    
    log "installing python setuptools"
    sudo -u $SUDO_USER wget -q http://peak.telecommunity.com/dist/ez_setup.py -O /tmp/ez_setup.py
    python /tmp/ez_setup.py -U setuptools
    
    log "installing virtualenv"
    easy_install virtualenv
}

function main() {
    uname=$(uname)
    
    if [ "$SUDO_USER" == "" ]
    then
        echo "FATAL: SUDO_USER is not set." 1>&2
        exit 2
    fi

    if [ "$uname" == "Darwin" ]
    then
        install_macosx_dependencies
    else
        install_linux_dependencies
    fi
}

if [ "$USER" == "root" ]
then
    main
else
    echo "This script must be run as root." 1>&2
    exit 1
fi
