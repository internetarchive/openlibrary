chdir /usr/local/solr
sleep 5
java -Xms2000m -Xmx2000m -Dsolr.solr.home=$1 -Dsolr.data.dir=$2 -Djetty.port=$3 -jar start.jar
