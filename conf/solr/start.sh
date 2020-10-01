#!/bin/bash

# Default to dev env
ENV=${ENV:-dev}
# How much memory to use
JAVA_MEM=${JAVA_MEM:-}

ln -sf /etc/solr/conf/solrconfig-$ENV.xml /etc/solr/conf/solrconfig.xml

# On dev, don't use haproxy; make tomcat serve directly to 8983
if [ "$ENV" = "dev" ] ; then
    sed -i 's/8080/8983/g' /var/lib/tomcat7/conf/server.xml;
fi

if [ "$ENV" = "prod" ] ; then
    # Default to 10 G of memory on prod
    JAVA_MEM="${JAVA_MEM:-10g}"

    # Load balance with haproxy
    service haproxy start
fi

# Set Tomcat's java options
TOMCAT_JAVA_OPTS='-Djava.awt.headless=true -XX:+UseConcMarkSweepGC'
if [ -n "$JAVA_MEM" ] ; then
  TOMCAT_JAVA_OPTS="${TOMCAT_JAVA_OPTS} -Xmx${JAVA_MEM} -Xms${JAVA_MEM}"
fi;
echo 'export JAVA_OPTS="${JAVA_OPTS} '"${TOMCAT_JAVA_OPTS}"'"' > /usr/share/tomcat7/bin/setenv.sh

/usr/share/tomcat7/bin/catalina.sh run
