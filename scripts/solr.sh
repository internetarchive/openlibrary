#! /bin/bash
#
# Script to start and stop solr in the dev-instance.
#


NAME="Solr"
ROOT=$PWD
LOG_FILE=var/log/solr.log
PIDFILE=var/run/solr.pid
SOLR_HOME=usr/local/solr/example
START_COMMAND="java -Dsolr.solr.home=../../../../conf/solr-biblio -Dsolr.data.dir=../../../../var/lib/solr -jar start.jar"

start() {
  echo "Starting $NAME"

  if [ -f $PIDFILE ]; then
    echo "$PIDFILE exists. $NAME may be running."
  else
    cd $SOLR_HOME
    $START_COMMAND > $ROOT/$LOG_FILE 2>&1 &
    sleep 2
    echo `ps -ef | grep -v grep | grep "$START_COMMAND" | awk '{print $2}'` > $ROOT/$PIDFILE
    echo "Done. Output is logged to $LOG_FILE."
  fi
  return 0
}

stop() {
  echo "Stopping $NAME"
  kill `cat $PIDFILE`
  rm $PIDFILE
  echo "Done"
  return 0
}

status() {
  if [ -f $PIDFILE ]; then
    echo "$NAME running with pid `cat $PIDFILE`."
  else
    echo "$NAME is not running"
  fi
}

case "$1" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    status)
        status
        ;;
    restart)
        stop
        sleep 2
        start
        ;;
    *)
        echo "Usage: $0 (start | stop | restart)"
        exit 1
esac

exit $?

