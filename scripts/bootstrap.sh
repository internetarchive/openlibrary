#! /bin/bash
# Bootstrap script to setup vagrant dev-instance for Open Library

# Set the locale to POSIX
# Important to do this before installing postgresql
update-locale LANG=en_US.UTF-8 LC_ALL=POSIX

#apt-get update

APT_PACKAGES="
nginx
solr-tomcat
postgresql
build-essential
curl
git-core

libgeoip-dev

python-dev
python-pip
python-lxml
python-beautifulsoup
python-babel
python-imaging
python-couchdb
python-genshi
gunicorn
python-psycopg2
python-py
python-memcache
python-yaml
python-simplejson
python-sphinx
python-celery
python-sqlalchemy"

apt-get install -y $APT_PACKAGES

PYTHON_PACKAGES="
DBUtils==1.1
iptools==0.4.0
pymarc==2.8.4
web.py==0.33
pystatsd==0.1.6
eventer==0.1.1
OL-GeoIP==1.2.4
mockcache"

pip install $PYTHON_PACKAGES
