#!/usr/bin/python
import os, urllib2, os.path, shutil

filename = 'apache-solr-1.4.0.tgz'
solr_dir = 'apache-solr-1.4.0'
url = 'http://www.apache.org/dist/lucene/solr/1.4.0/' + filename

def cp_file(src, dst):
    print "copy '%s' to '%s'" % (src, dst)
    shutil.copy(src, dst)

os.chdir('vendor')
if not os.path.exists(filename):
    os.system('wget ' + url)
if not os.path.exists(solr_dir):
    os.system('tar zxf ' + filename)

types = 'authors', 'editions', 'works', 'subjects'
for d in ['solr', 'solr/solr'] + ['solr/solr/' + t for t in types]:
    if not os.path.exists(d):
        os.mkdir(d)

cp = ['etc', 'lib', 'logs', 'webapps']
for i in cp:
    if not os.path.exists('solr/' + i):
        shutil.copytree(solr_dir + '/example/' + i, 'solr/' + i)

f = 'start.jar'
cp_file(solr_dir + '/example/' + f, 'solr/' + f)

f = 'solr.xml'
cp_file('../conf/solr-biblio/solr.xml', 'solr/solr/' + f)

for t in types:
    if not os.path.exists('solr/solr/' + t + '/conf'):
        shutil.copytree(solr_dir + '/example/solr/conf', 'solr/solr/' + t + '/conf')
    cp_file('../conf/solr-biblio/' + t + '.xml', 'solr/solr/' + t + '/conf/schema.xml')
    f = 'solr/solr/' + t + '/conf/solrconfig.xml'
    print "writing '%s'" % f
    out = open(f, 'w')
    for line in open(solr_dir + '/example/solr/conf/solrconfig.xml'):
        if '<dataDir>' in line:
            line = '  <dataDir>${solr.data.dir:./solr/%s/data}</dataDir>\n' % t
        out.write(line)
    out.close()
