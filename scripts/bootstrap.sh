#! /bin/bash
# Bootstrap script to setup vagrant dev-instance for Open Library

# Set the locale to POSIX
# Important to do this before installing postgresql
update-locale LANG=en_US.UTF-8 LC_ALL=POSIX

apt-get update

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

function setup_database() {
    echo "finding if posgres user vagrant already exists."
    x=`sudo -u postgres psql -t -c "select count(*) FROM pg_catalog.pg_user where usename='vagrant'"`
    echo "result = $x"
    if [ "$x" -eq 0 ]; then
        echo "setting up database..."
        echo "  creating postgres user 'vagrant'"
        sudo -u postgres createuser -s vagrant

        echo "  creating openlibrary database"
        sudo -u vagrant createdb openlibrary

        echo " setting up openlibrary database"
        setup_ol
    else
        echo "pg_user vagrant already exists. no need to setup database"
    fi
}

function setup_ol() {
    cd /vagrant
    sed -e 's/hybrid/local/' -e 's/^infobase_server/# infobase_server/' conf/openlibrary.yml > conf/ol-install.yml
    sudo -u vagrant python scripts/openlibrary-server conf/ol-install.yml install
    #rm conf/ol-install.yml
}

function setup_nginx() {
    ln -sf /vagrant/conf/nginx/sites-available/openlibrary.conf /etc/nginx/sites-available/
    ln -sf /etc/nginx/sites-available/openlibrary.conf /etc/nginx/sites-enabled/
    sudo /etc/init.d/nginx restart
}

pip install $PYTHON_PACKAGES

setup_database
setup_nginx

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
