#! /bin/bash
# Bootstrap script to setup vagrant dev-instance for Open Library
set -e

# @@@ Change the following 2 lines if you want to install OL from a different place or as a different user
OL_ROOT=/openlibrary
OL_USER=vagrant

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
python-sqlalchemy
python-pytest"

apt-get install -y $APT_PACKAGES

PYTHON_PACKAGES="
DBUtils==1.1
iptools==0.4.0
pymarc==2.8.4
web.py==0.33
pystatsd==0.1.6
eventer==0.1.1
OL-GeoIP==1.2.4
mockcache
sixpack-client"

REINDEX_SOLR=no

function setup_database() {
    echo "finding if posgres user vagrant already exists."
    x=`sudo -u postgres psql -t -c "select count(*) FROM pg_catalog.pg_user where usename='$OL_USER'"`
    echo "result = $x"
    if [ "$x" -eq 0 ]; then
        echo "setting up database..."
        echo "  creating postgres user 'OL_USER'"
        sudo -u postgres createuser -s $OL_USER

        echo "  creating openlibrary database"
        sudo -u $OL_USER createdb openlibrary
        sudo -u $OL_USER createdb coverstore
        sudo -u $OL_USER psql coverstore < $OL_ROOT/openlibrary/coverstore/schema.sql

        echo " setting up openlibrary database"
        setup_ol
        REINDEX_SOLR=yes
    else
        echo "pg_user $OL_USER already exists. no need to setup database"
    fi
}

function setup_ol() {
    # Download sample dev-instance database from archive.org
    wget https://archive.org/download/ol_vendor/openlibrary-devinstance.pg_dump.gz -O /tmp/openlibrary-devinstance.pg_dump.gz
    zcat /tmp/openlibrary-devinstance.pg_dump.gz | sudo -u $OL_USER psql openlibrary

    # This is an alternative way to install OL from scratch
    #cd $OL_ROOT
    #sed -e 's/hybrid/local/' -e 's/^infobase_server/# infobase_server/' conf/openlibrary.yml > conf/ol-install.yml
    #sudo -u $OL_ROOT python scripts/openlibrary-server conf/ol-install.yml install
    #rm conf/ol-install.yml
}

function setup_nginx() {
    ln -sf $OL_ROOT/conf/nginx/sites-available/openlibrary.conf /etc/nginx/sites-available/
    ln -sf /etc/nginx/sites-available/openlibrary.conf /etc/nginx/sites-enabled/
    if [ -f /etc/nginx/sites-enabled/default ]; then
        rm /etc/nginx/sites-enabled/default
    fi
    sudo /etc/init.d/nginx restart
}

# pip version 1.5.4 gets into some issues when old version of requests is installed.
# get the latest version of pip in that case
# if pip --version | grep -q 1.5.4
# then
#     pip install -U pip
# fi

easy_install pip

pip install $PYTHON_PACKAGES

setup_database
setup_nginx

# change solr/tomcat port to 8983
perl -i -pe 's/8080/8983/'  /etc/tomcat6/server.xml
cp $OL_ROOT/conf/solr/conf/schema.xml /etc/solr/conf/
/etc/init.d/tomcat6 restart

mkdir -p /var/log/openlibrary /var/lib/openlibrary
chown $OL_USER:$OL_USER /var/log/openlibrary /var/lib/openlibrary

# run make to initialize git submodules, build css and js files
cd $OL_ROOT && make

cp $OL_ROOT/conf/init/* /etc/init/
cd $OL_ROOT/conf/init
for name in ol-*
do
	echo starting ${name//.conf}
	initctl start ${name//.conf} || initctl restart ${name//.conf}
done

if [ "$REINDEX_SOLR" == "yes" ]
then
    cd $OL_ROOT
    sudo -u $OL_USER make reindex-solr
fi

echo "sudo service nginx restart
cd /openlibrary/conf/init
for name in ol-*; do echo starting ${name//.conf}; sudo initctl start ${name//.conf} || sudo initctl restart ${name//.conf}; done" > /etc/init.d/ol-start

chmod +x /etc/init.d/ol-start

echo "/etc/init.d/ol-start
exit 0" > /etc/rc.local
