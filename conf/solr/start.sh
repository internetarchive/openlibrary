#!/bin/bash

# Default to dev env
ENV=${ENV:-dev}

ln -sf /etc/solr/conf/solrconfig-$ENV.xml /etc/solr/conf/solrconfig.xml

# On dev, don't use haproxy; make tomcat serve directly to 8983
if [ "$ENV" = "dev" ] ; then
    sed -i 's/8080/8983/g' /var/lib/tomcat7/conf/server.xml;
fi

if [ "$ENV" = "prod" ] ; then
    # Use more memory
    echo 'export JAVA_OPTS="${JAVA_OPTS} -Djava.awt.headless=true -Xmx10g -Xms10g -XX:+UseConcMarkSweepGC"' > /usr/share/tomcat7/bin/setenv.sh
    # Load balance with haproxy
    service haproxy start
fi

/usr/share/tomcat7/bin/catalina.sh run
