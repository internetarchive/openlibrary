#!/bin/bash

# Updates the GeoIP database

CITY_DATABASE=GeoLiteCity.dat
CITY_DATABASE_URL=http://geolite.maxmind.com/download/geoip/database/${CITY_DATABASE}.gz
GEOIP_DIR=`dirname $0`/../usr/local/GeoIP

mkdir -p $GEOIP_DIR
cd $GEOIP_DIR

echo Getting database from $CITY_DATABASE_URL
wget -q -N $CITY_DATABASE_URL

gunzip < $CITY_DATABASE.gz > $CITY_DATABASE.tmp
mv $CITY_DATABASE.tmp $CITY_DATABASE

# $$$ Tell OL to update to new database