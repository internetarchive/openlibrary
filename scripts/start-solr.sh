export SOLR=/usr/local/solr
cd $1
java -Xms2000m -Xmx2000m -Dsolr.solr.home=$1 -Dsolr.data.dir=$2 -Djetty.port=$3 -jar $SOLR/example/start.jar
