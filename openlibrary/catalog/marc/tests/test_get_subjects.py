from pathlib import Path

import lxml.etree
import pytest
from lxml import etree

from openlibrary.catalog.marc.get_subjects import four_types, read_subjects
from openlibrary.catalog.marc.marc_binary import MarcBinary
from openlibrary.catalog.marc.marc_xml import MarcXml

xml_samples = [
    ('bijouorannualofl1828cole', {}),
    ('flatlandromanceo00abbouoft', {}),
    ('lesabndioeinas00sche', {}),
    ('onquietcomedyint00brid', {}),
    ('zweibchersatir01horauoft', {}),
    ('00schlgoog', {'subject': {'Jewish law': 1}}),
    (
        '0descriptionofta1682unit',
        {
            'place': {'United States': 1},
            'subject': {
                "Decedents' estates": 1,
                'Taxation': 1,
                'S. 1983 97th Congress': 1,
                'S. 2479 97th Congress': 1,
            },
        },
    ),
    (
        '13dipolarcycload00burk',
        {
            'subject': {
                'Allene': 1,
                'Ring formation (Chemistry)': 1,
                'Trimethylenemethane': 1,
            }
        },
    ),
    (
        '1733mmoiresdel00vill',
        {'place': {'Spain': 1}, 'subject': {'Courts and court life': 1, 'History': 1}},
    ),
    (
        '39002054008678_yale_edu',
        {
            'place': {'Ontario': 2},
            'subject': {'Description and travel': 1, 'History': 1},
        },
    ),
    (
        'abhandlungender01ggoog',
        {
            'place': {'Lusatia': 1, 'Germany': 1},
            'subject': {'Natural history': 2, 'Periodicals': 1},
        },
    ),
    (
        'nybc200247',
        {
            'person': {'Simon Dubnow (1860-1941)': 1},
            'subject': {'Philosophy': 1, 'Jews': 1, 'History': 1},
        },
    ),
    (
        'scrapbooksofmoun03tupp',
        {
            'person': {'William Vaughn Tupper (1835-1898)': 1},
            'subject': {
                'Photographs': 4,
                'Sources': 1,
                'Description and travel': 2,
                'Travel': 1,
                'History': 1,
                'Travel photography': 1,
            },
            'place': {'Europe': 3, 'Egypt': 2},
            'time': {'19th century': 1},
        },
    ),
    ('secretcodeofsucc00stjo', {'subject': {'Success in business': 1}}),
    (
        'warofrebellionco1473unit',
        {
            'time': {'Civil War, 1861-1865': 2},
            'place': {'United States': 2, 'Confederate States of America': 1},
            'subject': {'Sources': 2, 'Regimental histories': 1, 'History': 3},
        },
    ),
]

bin_samples = [
    ('bpl_0486266893.mrc', {}),
    ('flatlandromanceo00abbouoft_meta.mrc', {}),
    ('lc_1416500308.mrc', {}),
    ('talis_245p.mrc', {}),
    ('talis_740.mrc', {}),
    ('talis_empty_245.mrc', {}),
    ('talis_multi_work_tiles.mrc', {}),
    ('talis_no_title2.mrc', {}),
    ('talis_no_title.mrc', {}),
    ('talis_see_also.mrc', {}),
    ('talis_two_authors.mrc', {}),
    ('zweibchersatir01horauoft_meta.mrc', {}),
    (
        '1733mmoiresdel00vill_meta.mrc',
        {'place': {'Spain': 1}, 'subject': {'Courts and court life': 1, 'History': 1}},
    ),
    (
        'collingswood_520aa.mrc',
        {
            'subject': {
                'Learning disabilities': 1,
                'People with disabilities': 1,
                'Talking books': 1,
                'Juvenile literature': 1,
                'Juvenile fiction': 3,
                'Friendship': 1,
            }
        },
    ),
    ('collingswood_bad_008.mrc', {'subject': {'War games': 1, 'Battles': 1}}),
    (
        'histoirereligieu05cr_meta.mrc',
        {'org': {'Jesuits': 2}, 'subject': {'Influence': 1, 'History': 1}},
    ),
    (
        'ithaca_college_75002321.mrc',
        {
            'place': {'New Jersey': 3},
            'subject': {
                'Congresses': 3,
                'Negative income tax': 1,
                'Guaranteed annual income': 1,
                'Labor supply': 1,
            },
        },
    ),
    (
        'ithaca_two_856u.mrc',
        {'place': {'Great Britain': 2}, 'subject': {'Statistics': 1, 'Periodicals': 2}},
    ),
    (
        'lc_0444897283.mrc',
        {
            'subject': {
                'Shipyards': 1,
                'Shipbuilding': 1,
                'Data processing': 2,
                'Congresses': 3,
                'Naval architecture': 1,
                'Automation': 1,
            }
        },
    ),
    (
        'ocm00400866.mrc',
        {'subject': {'School songbooks': 1, 'Choruses (Mixed voices) with piano': 1}},
    ),
    (
        'scrapbooksofmoun03tupp_meta.mrc',
        {
            'person': {'William Vaughn Tupper (1835-1898)': 1},
            'subject': {
                'Photographs': 4,
                'Sources': 1,
                'Description and travel': 2,
                'Travel': 1,
                'History': 1,
                'Travel photography': 1,
            },
            'place': {'Europe': 3, 'Egypt': 2},
            'time': {'19th century': 1},
        },
    ),
    ('secretcodeofsucc00stjo_meta.mrc', {'subject': {'Success in business': 1}}),
    (
        'talis_856.mrc',
        {
            'subject': {
                'Politics and government': 1,
                'Jewish-Arab relations': 1,
                'Middle East': 1,
                'Arab-Israeli conflict': 1,
            },
            'time': {'1945-': 1},
        },
    ),
    (
        'uoft_4351105_1626.mrc',
        {'subject': {'Aesthetics': 1, 'History and criticism': 1}},
    ),
    (
        'upei_broken_008.mrc',
        {'place': {'West Africa': 1}, 'subject': {'Social life and customs': 1}},
    ),
    (
        'upei_short_008.mrc',
        {
            'place': {'Charlottetown (P.E.I.)': 1, 'Prince Edward Island': 1},
            'subject': {
                'Social conditions': 1,
                'Economic conditions': 1,
                'Guidebooks': 1,
                'Description and travel': 2,
            },
        },
    ),
    (
        'warofrebellionco1473unit_meta.mrc',
        {
            'time': {'Civil War, 1861-1865': 2},
            'place': {'United States': 2, 'Confederate States of America': 1},
            'subject': {'Sources': 2, 'Regimental histories': 1, 'History': 3},
        },
    ),
    (
        'wrapped_lines.mrc',
        {
            'org': {
                'United States. Congress. House. Committee on Foreign Affairs': 1,
            },
            'place': {'United States': 1},
            'subject': {'Foreign relations': 1},
        },
    ),
    (
        'wwu_51323556.mrc',
        {
            'subject': {
                'Statistical methods': 1,
                'Spatial analysis (Statistics)': 1,
                'Population geography': 1,
            }
        },
    ),
]

record_tag = '{http://www.loc.gov/MARC21/slim}record'
TEST_DATA = Path(__file__).with_name('test_data')


class TestSubjects:
    @pytest.mark.parametrize(('item', 'expected'), xml_samples)
    def test_subjects_xml(self, item, expected):
        filepath = TEST_DATA / 'xml_input' / f'{item}_marc.xml'
        element = etree.parse(
            filepath, parser=lxml.etree.XMLParser(resolve_entities=False)
        ).getroot()
        if element.tag != record_tag and element[0].tag == record_tag:
            element = element[0]
        rec = MarcXml(element)
        assert read_subjects(rec) == expected

    @pytest.mark.parametrize(('item', 'expected'), bin_samples)
    def test_subjects_bin(self, item, expected):
        filepath = TEST_DATA / 'bin_input' / item
        rec = MarcBinary(filepath.read_bytes())
        assert read_subjects(rec) == expected

    def test_four_types_combine(self):
        subjects = {'subject': {'Science': 2}, 'event': {'Party': 1}}
        expect = {'subject': {'Science': 2, 'Party': 1}}
        assert four_types(subjects) == expect

    def test_four_types_event(self):
        subjects = {'event': {'Party': 1}}
        expect = {'subject': {'Party': 1}}
        assert four_types(subjects) == expect
