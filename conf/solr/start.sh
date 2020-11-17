#!/bin/bash

ln -sf /etc/solr/${SOLR_CONFIG} /etc/solr/conf/solrconfig.xml

if [ "$HAPROXY" = "true" ] ; then
  # Load balance with haproxy
  service haproxy start
else
  # Not using haproxy; make tomcat serve directly to 8983
  sed -i 's/8080/8983/g' /var/lib/tomcat7/conf/server.xml;
fi;

# Set Tomcat's java options
TOMCAT_JAVA_OPTS='-Djava.awt.headless=true -XX:+UseConcMarkSweepGC'
if [ -n "$EXTRA_TOMCAT_JAVA_OPTS" ] ; then
  TOMCAT_JAVA_OPTS="${TOMCAT_JAVA_OPTS} ${EXTRA_TOMCAT_JAVA_OPTS}"
fi;
echo 'export JAVA_OPTS="${JAVA_OPTS} '"${TOMCAT_JAVA_OPTS}"'"' > /usr/share/tomcat7/bin/setenv.sh

/usr/share/tomcat7/bin/catalina.sh run
