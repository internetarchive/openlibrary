# solr start script

cd /opt/openlibrary/production/vendor/solr

java -Xms2g -Xmx5g -jar start.jar >> /var/log/openlibrary/solr.log
