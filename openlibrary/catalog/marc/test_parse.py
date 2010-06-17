#!/usr/bin/python
import unittest

from parse import read_edition
from marc_binary import MarcBinary
from marc_xml import MarcXml, BadSubtag, BlankTag
from pprint import pprint
from urllib import urlopen
from lxml import etree

samples = ['warofrebellionco1473unit', 'flatlandromanceo00abbouoft', 'secretcodeofsucc00stjo']
samples = ['warofrebellionco1473unit'], #'flatlandromanceo00abbouoft', 'secretcodeofsucc00stjo']
samples = ['zweibchersatir01horauoft']

def whatever():
    count = 0
    for line in open('/2/edward/ia/scanned_books'):
        count += 1
        if count < 100:
            continue
        count = 0
        cur = eval(line)
        item = cur['identifier']
        yield item

#item = whatever()
#print item

record_tag = '{http://www.loc.gov/MARC21/slim}record'

class TestParse(unittest.TestCase):
    for i in whatever():
#        if i != 'apocalypseofabrabgh00boxg':
#            continue
#        if i != 'cu31924024927323':
#            continue
#        if i != 'deeringofdealors00gris':
#            continue
#        if i != 'iconographiegn50jang':
#            continue
#        if i < 'canterburyyork48unknuoft':
#            continue
#        if i != 'behullhglorygod00macngoog':
#            continue
        if i == 'akademiesocialis10vprauoft':
            continue

        print i
        marc_xml_url = 'http://www.archive.org/download/' + i + '/' + i + '_marc.xml'
        marc_bin_url = 'http://www.archive.org/download/' + i + '/' + i + '_meta.mrc'
        #f = open('test_data/' + i + '_meta.mrc')
        f = urlopen(marc_bin_url)
        data = f.read()
        #print 'binary:', `data`
        if '<title>Internet Archive: Page Not Found</title>' in data:
            continue
        if '<title>Internet Archive: Error</title>' in data:
            f = urlopen(marc_bin_url)
            data = f.read()
            if '<title>Internet Archive: Error</title>' in data:
                continue

        if data == '': # empty
            continue
        #rec = MarcBinary(data, ia=True)
        rec = MarcBinary(data)
        edition_marc_bin = read_edition(rec)

        element = etree.parse(urlopen(marc_xml_url)).getroot()
        if element.tag != record_tag and element[0].tag == record_tag:
            element = element[0]
        #f = open('test_data/' + i + '_marc.xml')
        rec = MarcXml(element)
        try:
            edition_marc_xml = read_edition(rec)
        except BadSubtag:
            continue
        except BlankTag:
            print 'blank tag'
            continue

        print 'XML'
        pprint(edition_marc_xml)
        print
        print 'Binary'
        pprint(edition_marc_bin)
        print

        assert edition_marc_bin.keys() == edition_marc_xml.keys()

        for k in edition_marc_bin.keys():
            if edition_marc_bin[k] != edition_marc_xml[k]:
                print k
                print '  bin:', `edition_marc_bin[k]`
                print '  xml:', `edition_marc_xml[k]`

#        assert edition_marc_bin == edition_marc_xml
