from marc_xml import MarcXml, BadSubtag, BlankTag
from lxml import etree
from marc_binary import MarcBinary
from marc_subject import read_subjects, tidy_subject, four_types
from collections import defaultdict

xml_samples = [
    ('bijouorannualofl1828cole', {}),
    ('flatlandromanceo00abbouoft', {}),
    ('lesabndioeinas00sche', {}),
    ('onquietcomedyint00brid', {}),
    ('zweibchersatir01horauoft', {}),

    ('00schlgoog',
        {'subject': {u'Jewish law': 1}}),
    ('0descriptionofta1682unit', {
        'place': {u'United States': 1},
        'subject': {u"Decedents' estates": 1, u'Taxation': 1, u'S. 1983 97th Congress': 1, u'S. 2479 97th Congress': 1}
    }),
    ('13dipolarcycload00burk',
        {'subject': {u'Allene': 1, u'Ring formation (Chemistry)': 1, u'Trimethylenemethane': 1}}),
    ('1733mmoiresdel00vill',
        {'place': {u'Spain': 1}, 'subject': {u'Courts and court life': 1, u'History': 1}}),
    ('39002054008678.yale.edu',
        {'place': {u'Ontario': 2}, 'subject': {u'Description and travel': 1, u'History': 1}}),
    ('abhandlungender01ggoog',
        {'place': {u'Lusatia': 1, u'Germany': 1}, 'subject': {u'Natural history': 2, u'Periodicals': 1}}),
    ('nybc200247',
        {'person': {u'Simon Dubnow (1860-1941)': 1}, 'subject': {u'Philosophy': 1, u'Jews': 1, u'History': 1}}),
    ('scrapbooksofmoun03tupp', {
        'person': {u'William Vaughn Tupper (1835-1898)': 1},
        'subject': {u'Photographs': 4, u'Sources': 1, u'Description and travel': 2, u'Travel': 1, u'History': 1, u'Travel photography': 1},
        'place': {u'Europe': 3, u'Egypt': 2},
        'time': {u'19th century': 1}}),
    ('secretcodeofsucc00stjo',
        {'subject': {u'Success in business': 1}}),
    ('warofrebellionco1473unit', {
        'time': {u'Civil War, 1861-1865': 2},
        'place': {u'United States': 2, u'Confederate States of America': 1},
        'subject': {u'Sources': 2, u'Regimental histories': 1, u'History': 3}}),
]

bin_samples = [
    ('bpl_0486266893', {}),
    ('flatlandromanceo00abbouoft_meta.mrc', {}),
    ('lc_1416500308', {}),
    ('talis_245p.mrc', {}),
    ('talis_740.mrc', {}),
    ('talis_empty_245.mrc', {}),
    ('talis_multi_work_tiles.mrc', {}),
    ('talis_no_title2.mrc', {}),
    ('talis_no_title.mrc', {}),
    ('talis_see_also.mrc', {}),
    ('talis_two_authors.mrc', {}),
    ('zweibchersatir01horauoft_meta.mrc', {}),

    ('1733mmoiresdel00vill_meta.mrc',
        {'place': {u'Spain': 1}, 'subject': {u'Courts and court life': 1, u'History': 1}}),
    ('collingswood_520aa.mrc',
        {'subject': {u'Learning disabilities': 1, u'People with disabilities': 1, u'Talking books': 1, u'Juvenile literature': 1, u'Juvenile fiction': 3, u'Friendship': 1}}),
    ('collingswood_bad_008.mrc',
        {'subject': {u'War games': 1, u'Battles': 1}}),
    ('histoirereligieu05cr_meta.mrc',
        {'org': {u'Jesuits': 4}, 'subject': {u'Influence': 1, u'History': 1}}),
    ('ithaca_college_75002321', {
        'place': {u'New Jersey': 3},
        'subject': {u'Congresses': 3, u'Negative income tax': 1, u'Guaranteed annual income': 1, u'Labor supply': 1}}),
    ('ithaca_two_856u.mrc', {
        'place': {u'Great Britain': 2},
        'subject': {u'Statistics': 1, u'Periodicals': 2}}),
    ('lc_0444897283',
        {'subject': {u'Shipyards': 1, u'Shipbuilding': 1, u'Data processing': 2, u'Congresses': 3, u'Naval architecture': 1, u'Automation': 1}}),
    ('ocm00400866',
        {'subject': {u'School songbooks': 1, u'Choruses (Mixed voices) with piano': 1}}),
    ('scrapbooksofmoun03tupp_meta.mrc', {
        'person': {u'William Vaughn Tupper (1835-1898)': 1},
        'subject': {u'Photographs': 4, u'Sources': 1, u'Description and travel': 2, u'Travel': 1, u'History': 1, u'Travel photography': 1},
        'place': {u'Europe': 3, u'Egypt': 2},
        'time': {u'19th century': 1}}),
    ('secretcodeofsucc00stjo_meta.mrc',
        {'subject': {u'Success in business': 1}}),
    ('talis_856.mrc',
        {'subject': {u'Politics and government': 1, u'Jewish-Arab relations': 1, u'Middle East': 1, u'Arab-Israeli conflict': 1}, 'time': {u'1945-': 1}}),
    ('uoft_4351105_1626',
        {'subject': {u'Aesthetics': 1, u'History and criticism': 1}}),
    ('upei_broken_008.mrc',
        {'place': {u'West Africa': 1}, 'subject': {u'Social life and customs': 1}}),
    ('upei_short_008.mrc',
        {'place': {u'Charlottetown (P.E.I.)': 1, u'Prince Edward Island': 1}, 'subject': {u'Social conditions': 1, u'Economic conditions': 1, u'Guidebooks': 1, u'Description and travel': 2}}),
    ('warofrebellionco1473unit_meta.mrc',
        {'time': {u'Civil War, 1861-1865': 2}, 'place': {u'United States': 2, u'Confederate States of America': 1}, 'subject': {u'Sources': 2, u'Regimental histories': 1, u'History': 3}}),
    ('wrapped_lines',
        {'org': {u'United States': 1, u'United States. Congress. House. Committee on Foreign Affairs': 1}, 'place': {u'United States': 1}, 'subject': {u'Foreign relations': 1}}),
    ('wwu_51323556',
        {'subject': {u'Statistical methods': 1, u'Spatial analysis (Statistics)': 1, u'Population geography': 1}}),
]

record_tag = '{http://www.loc.gov/MARC21/slim}record'

class TestSubjects:
    def _test_subjects(self, rec, expect):
        print read_subjects(rec)
        assert read_subjects(rec) == expect

    def test_subjects_xml(self):
        for item, expect in xml_samples:
            #print item
            filename = 'test_data/' + item + '_marc.xml'
            element = etree.parse(filename).getroot()
            if element.tag != record_tag and element[0].tag == record_tag:
                element = element[0]
            rec = MarcXml(element)
            yield self._test_subjects, rec, expect

    def test_subjects_bin(self):
        for item, expect in bin_samples:
            filename = 'test_data/' + item

            data = open(filename).read()
            if len(data) != int(data[:5]):
                data = data.decode('utf-8').encode('raw_unicode_escape')
            rec = MarcBinary(data)
            yield self._test_subjects, rec, expect

subjects = []
for item, expect in xml_samples:
    filename = 'test_data/' + item + '_marc.xml'
    element = etree.parse(filename).getroot()
    if element.tag != record_tag and element[0].tag == record_tag:
        element = element[0]
    rec = MarcXml(element)
    subjects.append(read_subjects(rec))

for item, expect in bin_samples:
    filename = 'test_data/' + item

    data = open(filename).read()
    if len(data) != int(data[:5]):
        data = data.decode('utf-8').encode('raw_unicode_escape')
    rec = MarcBinary(data)
    subjects.append(read_subjects(rec))

all_subjects = defaultdict(lambda: defaultdict(int))
for a in subjects:
    for b, c in a.items():
        for d, e in c.items():
            all_subjects[b][d] += e

print four_types(dict((k, dict(v)) for k, v in all_subjects.items()))
