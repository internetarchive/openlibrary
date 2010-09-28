#! /usr/bin/awk -f
{ sum += $1; }
END {print sum/NR;}
