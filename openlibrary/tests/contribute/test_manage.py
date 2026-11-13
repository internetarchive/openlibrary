from types import SimpleNamespace

import pytest

from openlibrary.contribute import manage


@pytest.mark.parametrize(
    ("lang", "categories"),
    [("en", {"one", "other"}), ("ru", {"one", "few", "many", "other"}), ("ar", {"zero", "one", "two", "few", "many", "other"})],
)
def test_plural_forms_cover_each_category_of_the_language(monkeypatch, lang, categories):
    monkeypatch.setattr(manage, "get_request_lang", lambda: lang)
    monkeypatch.setattr("openlibrary.i18n.req_context", SimpleNamespace(get=lambda: SimpleNamespace(lang=lang)))
    forms = manage.plural_forms("%(count)s book", "%(count)s books")
    assert set(forms) == categories
    assert forms["one"] == "{count} book"
    assert forms["other"] == "{count} books"
