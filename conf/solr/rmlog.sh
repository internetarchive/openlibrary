#!/bin/sh
find /var/log/tomcat7/* -mtime 7 -exec rm {} \;
