# solr start script
# start-solr.sh SOLR_HOME DATA_DIR PORTNUM LOGDIR
#   SOLR_HOME is where all the config stuff is, i.e. solrconfig/solr-biblio
#   DATA_DIR is where the index files are
#   PORTNUM is the listening port
#   LOGDIR is where the log files will go
export SOLR=/usr/local/solr
cd $SOLR/example
java -Xms2000m -Xmx2000m \
  -Djava.util.logging.config.file=logging.properties \
  -Dsolr.solr.home=$1 -Dsolr.data.dir=$2 -Djetty.port=$3 \
  -Djetty.logs=$4 \
  -jar start.jar
