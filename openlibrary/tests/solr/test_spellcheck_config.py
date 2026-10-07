"""Guards on the spellchecker dictionary configuration.

The spellchecker in conf/solr/conf/solrconfig.xml builds its dictionary from the
indexed terms of a single field, so its suggestions are only as good as that field's
index analyzer. These tests pin the two properties that matter:

  1. the dictionary field is `title_suggest`, and
  2. the analyzer of whatever field is named has no stemmer,

because a regression on either silently reintroduces stem-shaped suggestions like
"televis" without failing any behavioural test.

These read the deployed configset (conf/solr/conf is mounted as the `olconfig`
configset in compose.yaml), so they test what actually ships.
"""

import pathlib
import re
import xml.etree.ElementTree as ET

import pytest

CONF_DIR = pathlib.Path(__file__).resolve().parents[3] / "conf" / "solr" / "conf"
SOLRCONFIG = CONF_DIR / "solrconfig.xml"
SCHEMA = CONF_DIR / "managed-schema.xml"


@pytest.fixture(scope="module")
def solrconfig():
    return ET.parse(SOLRCONFIG).getroot()


@pytest.fixture(scope="module")
def schema():
    return ET.parse(SCHEMA).getroot()


def spellchecker_field(solrconfig):
    """The field DirectSolrSpellChecker builds its dictionary from."""
    component = solrconfig.find(".//searchComponent[@name='spellcheck']")
    assert component is not None, "no spellcheck searchComponent in solrconfig.xml"
    assert component.get("class") == "solr.SpellCheckComponent"
    default = [sc for sc in component.findall("lst[@name='spellchecker']") if sc.findtext("str[@name='name']") == "default"]
    assert len(default) == 1, "expected exactly one spellchecker named 'default'"
    checker = default[0]
    assert checker.findtext("str[@name='classname']") == "solr.DirectSolrSpellChecker"
    field = checker.findtext("str[@name='field']")
    assert field, "the default spellchecker declares no <str name='field'>"
    return field


def field_type(schema, name):
    for field in schema.findall(".//field"):
        if field.get("name") == name:
            return field.get("type")
    return None


def index_filters(schema, type_name):
    """Names of the filters in a fieldType's index analyzer."""
    for ftype in schema.findall(".//fieldType"):
        if ftype.get("name") != type_name:
            continue
        index = ftype.find("analyzer[@type='index']")
        assert index is not None, f"fieldType {type_name} has no index analyzer"
        return {f.get("name") for f in index.findall("filter")}
    return None


def test_dictionary_field_is_title_suggest(solrconfig):
    """The dictionary must come from the non-stemming field."""
    assert spellchecker_field(solrconfig) == "title_suggest"


def test_dictionary_field_exists_in_schema(solrconfig, schema):
    """A dictionary field that is not in the schema makes every query fail."""
    field = spellchecker_field(solrconfig)
    assert field_type(schema, field), f"{field} is not declared in managed-schema.xml"


def test_dictionary_field_analyzer_does_not_stem(solrconfig, schema):
    """This is the regression that matters: a stemmer yields stem suggestions.

    `title` (text_en_splitting) ends in porterStem, which is why the dictionary used
    to offer "televis" and "competit". Guard the *named* field so that swapping the
    dictionary back to a stemmed field fails here.
    """
    field = spellchecker_field(solrconfig)
    filters = index_filters(schema, field_type(schema, field))
    assert filters is not None, f"no fieldType for {field}"
    stemmers = {"porterStem", "SnowballPorterStemmer", "stemmer"}
    assert not (filters & stemmers), (
        f"dictionary field {field!r} has a stemming filter {filters & stemmers}, so spellcheck suggestions will be stems rather than real words"
    )


def test_title_is_stemmed_which_is_why_it_is_not_the_dictionary(solrconfig, schema):
    """Documents *why* title_suggest is used, so the choice is not 'simplified' back.

    If this ever stops holding, revisit the dictionary field.
    """
    assert spellchecker_field(solrconfig) != "title"
    assert "porterStem" in (index_filters(schema, field_type(schema, "title")) or set())


def test_title_suggest_is_populated_by_copy_field(schema):
    """The dictionary must actually have content, with no reindex to perform."""
    copies = {(cf.get("source"), cf.get("dest")) for cf in schema.findall(".//copyField")}
    assert ("title", "title_suggest") in copies, "nothing copies title into title_suggest, so the spellchecker dictionary would be empty"


def test_dictionary_field_is_not_part_of_any_query_field_list():
    """Changing the dictionary field must not be able to affect search results.

    title_suggest is deliberately absent from the edismax qf/pf used by work and
    edition search, so redirecting the spellchecker at it cannot change matching or
    ranking. If a future change adds it to a query field list, this fails.
    """
    for path in ("openlibrary/plugins/worksearch/schemes/works.py", "openlibrary/plugins/worksearch/schemes/editions.py"):
        source = (pathlib.Path(__file__).resolve().parents[3] / path).read_text()
        for match in re.finditer(r'qf="([^"]*)"', source):
            assert "title_suggest" not in match.group(1).split(), f"{path} has title_suggest in a qf; the dictionary field would then influence search results"
