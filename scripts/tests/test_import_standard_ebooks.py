from scripts.import_standard_ebooks import map_data

SAMPLE_1 = {
    'id': 'https://standardebooks.org/ebooks/t-e-lawrence/seven-pillars-of-wisdom',
    'guidislink': True,
    'link': 'https://standardebooks.org/ebooks/t-e-lawrence/seven-pillars-of-wisdom',
    'dcterms_identifier': 'url:https://standardebooks.org/ebooks/t-e-lawrence/seven-pillars-of-wisdom',
    'title': 'Seven Pillars of Wisdom',
    'title_detail': {
        'type': 'text/plain',
        'language': None,
        'base': '',
        'value': 'Seven Pillars of Wisdom',
    },
    'authors': [
        {
            'name': 'T. E. Lawrence',
            'href': 'https://standardebooks.org/ebooks/t-e-lawrence',
        }
    ],
    'author_detail': {
        'name': 'T. E. Lawrence',
        'href': 'https://standardebooks.org/ebooks/t-e-lawrence',
    },
    'href': 'https://standardebooks.org/ebooks/t-e-lawrence',
    'author': 'T. E. Lawrence',
    'schema_alternatename': 'Thomas Edward Lawrence',
    'schema_sameas': 'http://id.loc.gov/authorities/names/n79097491',
    'published': '2022-01-01T22:32:49Z',
    'updated': '2024-06-03T21:26:42Z',
    'dcterms_language': 'en-GB',
    'dcterms_publisher': 'Standard Ebooks',
    'rights': 'Public domain in the United States. Users located outside of the United States must check their local laws before using this ebook. Original content released to the public domain via the Creative Commons CC0 1.0 Universal Public Domain Dedication.',  # noqa: E501
    'rights_detail': {
        'type': 'text/plain',
        'language': None,
        'base': '',
        'value': 'Public domain in the United States. Users located outside of the United States must check their local laws before using this ebook. Original content released to the public domain via the Creative Commons CC0 1.0 Universal Public Domain Dedication.',  # noqa: E501
    },
    'summary': 'T. E. Lawrence’s memoir of leading the Arab revolt against the Ottoman empire during World War I.',  # noqa: RUF001
    'summary_detail': {
        'type': 'text/plain',
        'language': None,
        'base': '',
        'value': 'T. E. Lawrence’s memoir of leading the Arab revolt against the Ottoman empire during World War I.',  # noqa: RUF001
    },
    'content': [
        {
            'type': 'text/html',
            'language': None,
            'base': '',
            'value': '<p><i>Seven Pillars of Wisdom</i> is <a href="https://standardebooks.org/ebooks/t-e-lawrence"><abbr>T. E.</abbr> Lawrence’s</a> memoir of his involvement in leading a portion of the Arab revolt against the Ottoman empire during World War I. The empire had joined the side of Germany and the Central Powers in the war, and Britain hoped that a successful revolt would take the empire out of the war effort. Britain had also promised the Arabs that, if they were successful, England would recognize a single Arab state.</p> <p>Lawrence convinced the Arab leaders, who had historically not shown a willingness to work together, to join forces in supporting Britain’s strategy in the area. His memoir is part travelogue, part philosophy treatise, and part action novel. It details his movements and actions during his two year involvement, his relationships with the various Arab leaders and men who fought with him, and his thoughts—and doubts—during that time. It’s a gripping tale made famous by the movie <i>Lawrence of Arabia</i>, and one that Winston Churchill called “unsurpassable” as a “narrative of war and adventure.”</p> <p>The manuscript of <i>Seven Pillars of Wisdom</i> has a rich history. Lawrence finished his first draft in 1919 from his notes during the war, but lost most of it when changing trains in England (it was never found). The next year, he started working on a new version from memory that ended up being sixty percent longer than the original. He then edited that version (although it was still a third longer than the original draft), finishing it in early 1922, and had eight copies of it printed to give to friends so they could review it and offer editing suggestions (and to prevent a repeat of losing his only copy). About this time he re-enlisted in the service, but friends convinced him to work on a version he could publish. In 1926, he had a first edition of approximately 200 copies published that included 125 black-and-white and color illustrations from sixteen different artists. The first edition lost money, and it was the only edition published during his lifetime. This edition uses the first edition text and includes all 125 of the original illustrations, including both endpapers.</p>',  # noqa: E501, RUF001
        }
    ],
    'tags': [
        {
            'term': 'Arab countries--History--Arab Revolt, 1916-1918',
            'scheme': 'http://purl.org/dc/terms/LCSH',
            'label': None,
        },
        {
            'term': 'World War, 1914-1918',
            'scheme': 'http://purl.org/dc/terms/LCSH',
            'label': None,
        },
        {
            'term': 'Adventure',
            'scheme': 'https://standardebooks.org/vocab/subjects',
            'label': None,
        },
        {
            'term': 'Memoir',
            'scheme': 'https://standardebooks.org/vocab/subjects',
            'label': None,
        },
        {
            'term': 'Nonfiction',
            'scheme': 'https://standardebooks.org/vocab/subjects',
            'label': None,
        },
    ],
    'links': [
        {
            'href': 'https://standardebooks.org/ebooks/t-e-lawrence/seven-pillars-of-wisdom/downloads/cover.jpg',
            'rel': 'http://opds-spec.org/image',
            'type': 'image/jpeg',
        },
        {
            'href': 'https://standardebooks.org/ebooks/t-e-lawrence/seven-pillars-of-wisdom/downloads/cover-thumbnail.jpg',
            'rel': 'http://opds-spec.org/image/thumbnail',
            'type': 'image/jpeg',
        },
        {
            'href': 'https://standardebooks.org/ebooks/t-e-lawrence/seven-pillars-of-wisdom',
            'rel': 'alternate',
            'title': 'This ebook’s page at Standard Ebooks',  # noqa: RUF001
            'type': 'application/xhtml+xml',
        },
        {
            'href': 'https://standardebooks.org/ebooks/t-e-lawrence/seven-pillars-of-wisdom/downloads/t-e-lawrence_seven-pillars-of-wisdom.epub',
            'length': '62070075',
            'rel': 'http://opds-spec.org/acquisition/open-access',
            'title': 'Recommended compatible epub',
            'type': 'application/epub+zip',
        },
        {
            'href': 'https://standardebooks.org/ebooks/t-e-lawrence/seven-pillars-of-wisdom/downloads/t-e-lawrence_seven-pillars-of-wisdom_advanced.epub',
            'length': '62221725',
            'rel': 'http://opds-spec.org/acquisition/open-access',
            'title': 'Advanced epub',
            'type': 'application/epub+zip',
        },
        {
            'href': 'https://standardebooks.org/ebooks/t-e-lawrence/seven-pillars-of-wisdom/downloads/t-e-lawrence_seven-pillars-of-wisdom.kepub.epub',
            'length': '62135106',
            'rel': 'http://opds-spec.org/acquisition/open-access',
            'title': 'Kobo Kepub epub',
            'type': 'application/kepub+zip',
        },
        {
            'href': 'https://standardebooks.org/ebooks/t-e-lawrence/seven-pillars-of-wisdom/downloads/t-e-lawrence_seven-pillars-of-wisdom.azw3',
            'length': '63108449',
            'rel': 'http://opds-spec.org/acquisition/open-access',
            'title': 'Amazon Kindle azw3',
            'type': 'application/x-mobipocket-ebook',
        },
    ],
}


def test_map_data():
    assert map_data(SAMPLE_1) == {
        "title": "Seven Pillars of Wisdom",
        "source_records": ["standard_ebooks:t-e-lawrence/seven-pillars-of-wisdom"],
        "publishers": ["Standard Ebooks"],
        "publish_date": "2022",
        "authors": [{"name": "T. E. Lawrence"}],
        "description": SAMPLE_1["content"][0]["value"],
        "subjects": [
            "Arab countries--History--Arab Revolt, 1916-1918",
            "World War, 1914-1918",
            "Adventure",
            "Memoir",
            "Nonfiction",
        ],
        "identifiers": {"standard_ebooks": ["t-e-lawrence/seven-pillars-of-wisdom"]},
        "languages": ["eng"],
        "cover": "https://standardebooks.org/ebooks/t-e-lawrence/seven-pillars-of-wisdom/downloads/cover.jpg",
    }
