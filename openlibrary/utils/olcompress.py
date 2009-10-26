"""Initial seed to create compress object.

see compress module for details.
"""

from compress import Compressor

# using 4 random records from OL seed

seed1= '{"subject_place": ["Great Britain", "Great Britain."], "lc_classifications": ["RT85.5 .K447 1994"], "contributions": ["Richardson, Eileen, RGN."], "id": 1875537, "title": "nursing process and quality care", "languages": [{"key": "/l/eng"}], "subjects": ["Nursing -- Quality control.", "Nursing -- Standards.", "Nursing audit.", "Nursing -- Great Britain -- Quality control.", "Nursing -- Standards -- Great Britain.", "Nursing audit -- Great Britain."], "publish_country": "cau", "title_prefix": "The ", "type": {"key": "/type/edition"}, "by_statement": "Nan Kemp, Eileen Richardson.", "revision": 1, "other_titles": ["Nursing process & quality care."], "publishers": ["Singular Pub. Group"], "last_modified": {"type": "/type/datetime", "value": "2008-04-01 03:28:50.625462"}, "key": "/b/OL1234567M", "authors": [{"key": "/a/OL448883A"}], "publish_places": ["San Diego, Calif"], "pagination": "132 p. :", "dewey_decimal_class": ["362.1/73/0685"], "notes": {"type": "/type/text", "value": "Includes bibliographical references and index.\nCover title: The nursing process & quality care."}, "number_of_pages": 132, "lccn": ["94237442"], "isbn_10": ["1565933834"], "publish_date": "1994"}'
seed2 = '{"subtitle": "exploration & celebration : papers delivered at an academic conference honoring twenty years of women in the rabbinate, 1972-1992", "subject_place": ["United States"], "lc_classifications": ["BM652 .W66 1996"], "contributions": ["Zola, Gary Phillip."], "id": 1523482, "title": "Women rabbis", "languages": [{"key": "/l/eng"}], "subjects": ["Women rabbis -- United States -- Congresses.", "Reform Judaism -- United States -- Congresses.", "Women in Judaism -- Congresses."], "publish_country": "ohu", "by_statement": "edited by Gary P. Zola.", "type": {"key": "/type/edition"}, "revision": 1, "publishers": ["HUC-JIR Rabbinic Alumni Association Press"], "last_modified": {"type": "/type/datetime", "value": "2008-04-01 03:28:50.625462"}, "key": "/b/OL987654M", "publish_places": ["Cincinnati"], "pagination": "x, 135 p. ;", "dewey_decimal_class": ["296.6/1/082"], "notes": {"type": "/type/text", "value": "Includes bibliographical references and index."}, "number_of_pages": 135, "lccn": ["96025781"], "isbn_10": ["0878202145"], "publish_date": "1996"}'
seed3 = '{"name": "W. Wilkins Davis", "personal_name": "W. Wilkins Davis", "death_date": "1866.", "last_modified": {"type": "/type/datetime", "value": "2008-08-21 07:57:48.336414"}, "key": "/a/OL948765A", "birth_date": "1842", "type": {"key": "/type/author"}, "id": 2985386, "revision": 2}'
seed4 = '{"name": "Alberto Tebechrani", "personal_name": "Alberto Tebechrani", "last_modified": {"type": "/type/datetime", "value": "2008-09-08 15:29:34.798941"}, "key": "/a/OL94792A", "type": {"key": "/type/author"}, "id": 238564, "revision": 2}'

seed = seed1 + seed2 + seed3 + seed4

def OLCompressor():
    """Create a compressor object for compressing OL data.
    """
    return Compressor(seed)