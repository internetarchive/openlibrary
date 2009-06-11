#! /bin/bash
# script to install all required software on OL nodes

# create OL folders
echo "creating folders..."

OL_FOLDERS="/0/pharos /1/pharos /2/pharos /3/pharos"
mkdir -p $OL_FOLDERS
chgrp  pharos $OL_FOLDERS
chmod g+w $OL_FOLDERS

echo "installing apt-get packages..."
aptitude install        \
    postgresql-client   \
    git-core            \
    sqlite3             \
    python-dev          \
    python-setuptools   \
    python-imaging      \
    python-psycopg2     \
    python-mysqldb      \
    python-yaml         \
    python-profiler

echo "installing solr..."
pushd /tmp
# temporary mirror location because archive.org homeserver is down
# use archive.org mirror once that situation is fixed @@
wget http://www.mirrorgeek.com/apache.org/lucene/solr/1.3.0/apache-solr-1.3.0.tgz
md5sum apache-solr-1.3.0.tgz > apache-solr-1.3.0.downloaded-md5
md5sum apache-solr-1.3.0.tgz |
  if cmp -s - apache-solr-1.3.0.expected-md5 ;
      then echo "solr md5 check ok" ;
      else echo "solr md5 checksum fails" ;
           exit 1 ;
  fi
rm apache-solr-1.3.0.downloaded-md5
mkdir -p /usr/local/solr-1.3.0
cd /usr/local/solr-1.3.0
tar xfz /tmp/apache-solr-1.3.0.tgz
rm /tmp/apache-solr-1.3.0.tgz
cd ..
ln -lf apache-solr-1.3.0 

echo "removing troublesome modules"
aptitude remove yaz

echo "installing python packages..."
easy_install -Z \
    simplejson  \
    pymarc      \
    web.py      \
    flup        \
    DBUtils     \
    subcommand

# setup code
echo "getting openlibrary code..."
dirs="/0/pharos/code /0/pharos/scripts /0/pharos/services /0/pharos/etc"
mkdir -p $dirs
chmod g+w $dirs
cd /0/pharos/code
git clone git://github.com/openlibrary/openlibrary.git

# fix lighttpd-angel hack used by petabox

sudo lighttpd-disable-mod petabox
sed 's,/petabox/sw/lighttpd/lighttpd-angel,/usr/sbin/lighttpd,' /etc/init.d/lighttpd > /tmp/lighttpd.$$
rm /etc/init.d/lighttpd # remove symlink to petabox
mv /tmp/lighttpd.$$ /etc/init.d/lighttpd
chmod +x /etc/init.d/lighttpd

mv /etc/lighttpd /etc/lighttpd.orig
ln -s /olsystem/etc/lighttpd /etc/lighttpd

# setup oldirs

oldirs=                         \
    /var/cache/openlibrary      \
    /0/pharos/data              \
    /1/pharos/data

mkdir $oldirs
chown openlibrary:openlibrary $oldirs

# setup shmmax to 2GB
echo 2147483648 > /proc/sys/kernel/shmmax
echo 2147483648 > /proc/sys/kernel/shmall

ln -s /olsystem/etc/sysctl.d/60-shm /etc/sysctl.d/

