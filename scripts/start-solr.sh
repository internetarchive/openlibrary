chdir /usr/local/solr
sleep 5
java -Xms2000m -Xmx2000m -Dsolr.data.dir=$1 -Djetty.port=$2 -jar start.jar
