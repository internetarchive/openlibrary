# chdir /usr/local/solr
chdir /home/phr/apache-solr-1.3.0/example/
sleep 5
java -Xms2000m -Xmx2000m -Dsolr.solr.home=$1 -Dsolr.data.dir=$2 -Djetty.port=$3 -jar start.jar
