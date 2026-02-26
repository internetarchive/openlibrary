from scripts.monitoring.solr_logs_monitor import RequestLogEntry, parse_log_entry

SAMPLE_LOG_LINE = """2025-01-14 20:50:33.796 INFO  (qtp1997548433-42-null-243439) [c: s: r: x:openlibrary t:null-243439] o.a.s.c.S.Request webapp=/solr path=/select params={q=({!edismax+q.op%3D"AND"+qf%3D"text+alternative_title^10+author_name^10"+pf%3D"alternative_title^10+author_name^10"+bf%3D"min(100,edition_count)+min(100,def(readinglog_count,0))"+v%3D$workQuery})&spellcheck=true&fl=*&start=0&fq=type:work&fq=ebook_access:[borrowable+TO+*]&spellcheck.count=3&sort=first_publish_year+desc&rows=12&workQuery=ebook_access:[borrowable+TO+*]+-key:"\\/works\\/OL4420181W"+author_key:(OL874808A)&wt=json} hits=2 status=0 QTime=12"""  # noqa: E501
SAMPLE_LOG_LINE_2 = """2025-08-19 10:08:55.140 INFO  (qtp693267461-23-null-396) [c: s: r: x:openlibrary t:null-396] o.a.s.c.S.Request webapp=/solr path=/select params={editions.fl=id_openstax,first_publish_year,ia_collection_s,edition_count,id_project_runeberg,ia,has_fulltext,cover_edition_key,subtitle,lending_identifier_s,id_standard_ebooks,cover_i,key,id_project_gutenberg,language,ebook_access,id_cita_press,id_librivox,lending_edition_s,public_scan_b,id_wikisource,title&ol.label=UNLABELLED&facet.field=subject_facet&facet.field=person_facet&facet.field=place_facet&facet.field=time_facet&fl=id_openstax,first_publish_year,ia_collection_s,edition_count,id_project_runeberg,ia,has_fulltext,cover_edition_key,subtitle,lending_identifier_s,author_name,id_standard_ebooks,cover_i,key,id_project_gutenberg,language,ebook_access,author_key,id_cita_press,id_librivox,lending_edition_s,public_scan_b,editions:[subquery],id_wikisource,title&userWorkQuery=*:*&editions.q=({!terms+f%3D_root_+v%3D$row.key})+AND+({!edismax+bq%3D"language:eng^40+ebook_access:public^10+ebook_access:borrowable^8+ebook_access:printdisabled^2+cover_i:*^2"+v%3D$userEdQuery+qf%3D"text+alternative_title^4+author_name^4"})&start=0&fq=type:work&fq=author_key:OL6848355A&sort=edition_count+desc&rows=20&editions.userEdQuery=*:*&editions.ol.label=EDITION_MATCH&facet.limit=25&q=%2B({!edismax+q.op%3D"AND"+qf%3D"text+alternative_title^10+author_name^10"+pf%3D"alternative_title^10+author_name^10"+bf%3D"min(100,edition_count)+min(100,def(readinglog_count,0))"+v%3D$userWorkQuery})+%2B(_query_:"{!parent+which%3Dtype:work+v%3D$fullEdQuery+filters%3D$editions.fq}"+OR+edition_count:0)&spellcheck=true&editions.rows=1&userEdQuery=*:*&fullEdQuery=({!edismax+bq%3D"language:eng^40+ebook_access:public^10+ebook_access:borrowable^8+ebook_access:printdisabled^2+cover_i:*^2"+v%3D$userEdQuery+qf%3D"text+alternative_title^4+author_name^4"})&spellcheck.count=3&editions.fq=type:edition&wt=json&facet=true} hits=1 status=0 QTime=4"""  # noqa: E501


class TestRequestLogEntry:
    def test_parse_log_line(self):
        entry = parse_log_entry(SAMPLE_LOG_LINE)
        assert isinstance(entry, RequestLogEntry)
        assert entry.timestamp == "2025-01-14 20:50:33.796"
        assert entry.log_level == "INFO"
        assert entry.thread_info == "qtp1997548433-42-null-243439"
        assert entry.context == "c: s: r: x:openlibrary t:null-243439"
        assert entry.class_handler == "o.a.s.c.S.Request"
        assert entry.webapp == "/solr"
        assert entry.path == "/select"
        assert (
            entry.params
            == '{q=({!edismax+q.op%3D"AND"+qf%3D"text+alternative_title^10+author_name^10"+pf%3D"alternative_title^10+author_name^10"+bf%3D"min(100,edition_count)+min(100,def(readinglog_count,0))"+v%3D$workQuery})&spellcheck=true&fl=*&start=0&fq=type:work&fq=ebook_access:[borrowable+TO+*]&spellcheck.count=3&sort=first_publish_year+desc&rows=12&workQuery=ebook_access:[borrowable+TO+*]+-key:"\\/works\\/OL4420181W"+author_key:(OL874808A)&wt=json}'  # noqa: E501
        )
        assert entry.status == 0
        assert entry.qtime == 12

    def test_parse_params(self):
        entry = parse_log_entry(SAMPLE_LOG_LINE)
        assert isinstance(entry, RequestLogEntry)
        assert entry.parse_params() == {
            "q": '({!edismax+q.op%3D"AND"+qf%3D"text+alternative_title^10+author_name^10"+pf%3D"alternative_title^10+author_name^10"+bf%3D"min(100,edition_count)+min(100,def(readinglog_count,0))"+v%3D$workQuery})',  # noqa: E501
            "spellcheck": "true",
            "fl": "*",
            "start": "0",
            "fq": ["type:work", "ebook_access:[borrowable+TO+*]"],
            "spellcheck.count": "3",
            "sort": "first_publish_year+desc",
            "rows": "12",
            "workQuery": 'ebook_access:[borrowable+TO+*]+-key:"\\/works\\/OL4420181W"+author_key:(OL874808A)',
            "wt": "json",
        }

    def test_label(self):
        entry = parse_log_entry(SAMPLE_LOG_LINE_2)
        assert isinstance(entry, RequestLogEntry)
        assert entry.parse_params().get("ol.label") == "UNLABELLED"
        assert entry.parse_params().get("editions.ol.label") == "EDITION_MATCH"
