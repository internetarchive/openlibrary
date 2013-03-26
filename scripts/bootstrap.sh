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
git-core
memcached

curl
screen

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

# For some wierd error, nginx doesn't seem to be starting on boot
/etc/init.d/nginx restart

# change solr/tomcat port to 8983
perl -i -pe 's/8080/8983/'  /etc/tomcat6/server.xml
cp /vagrant/conf/solr/conf/schema.xml /etc/solr/conf/
/etc/init.d/tomcat6 restart

mkdir -p /var/log/openlibrary /var/lib/openlibrary
chown vagrant:vagrant /var/log/openlibrary /var/lib/openlibrary

cp /vagrant/conf/init/* /etc/init/
cd /vagrant/conf/init 
for name in ol-*
do 
	echo starting ${name//.conf}
	start ${name//.conf}
done
