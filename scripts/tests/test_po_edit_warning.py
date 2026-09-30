from scripts.gh_scripts.po_edit_warning import (
    MARKER,
    affected_languages,
    overwrite_in_place,
    render_comment,
)

I18N = {"de", "es", "fr"}


def test_only_languages_openlibrary_i18n_has_are_affected():
    # `az` exists only in this repo, so #13070 leaves its file alone.
    changed = [
        "openlibrary/i18n/es/messages.po",
        "openlibrary/i18n/az/messages.po",
        "openlibrary/i18n/de/messages.po",
    ]
    assert affected_languages(changed, I18N) == ["de", "es"]


def test_other_i18n_files_are_not_translation_edits():
    changed = [
        "openlibrary/i18n/messages.pot",
        "openlibrary/i18n/es/messages.mo",
        "openlibrary/i18n/es/legacy-strings.es.yml",
        "openlibrary/i18n/__init__.py",
        "openlibrary/i18n/es/sub/messages.po",
        "vendor/openlibrary/i18n/es/messages.po",
        "openlibrary/i18n/es/messages.po.orig",
    ]
    assert affected_languages(changed, I18N) == []


def test_overwrite_is_detected_from_the_clone_in_dockerfile_olbase():
    before = "COPY --chown=openlibrary:openlibrary . /openlibrary\nRUN ln -s vendor/infogami/infogami infogami \\\n && make\n"
    # The step #13070 adds, verbatim.
    after = before.replace(
        "RUN ln -s",
        "# Pull latest translations from openlibrary-i18n (kept current by AI pipeline)\n"
        "RUN git clone --depth=1 https://github.com/internetarchive/openlibrary-i18n /tmp/i18n \\\n"
        " && rm -rf /tmp/i18n\n"
        "RUN ln -s",
    )
    assert not overwrite_in_place(before)
    assert overwrite_in_place(after)
    # Mentioning the repository is not cloning it.
    assert not overwrite_in_place(before + "# see openlibrary-i18n\n")


def test_comment_names_each_file_and_says_when_the_overwrite_applies():
    pending = render_comment(["de", "es"], in_place=False)
    live = render_comment(["de", "es"], in_place=True)

    for body in (pending, live):
        assert body.startswith(MARKER)
        assert "`openlibrary/i18n/de/messages.po`" in body
        assert "`openlibrary/i18n/es/messages.po`" in body
        assert "internetarchive/openlibrary-i18n" in body

    assert "Once #13070 lands" in pending
    assert "Once #13070 lands" not in live
    # Before the flip, a translator moving to openlibrary-i18n must learn the change is delayed, not lost.
    assert "reaches openlibrary.org when #13070 ships" in pending
    assert "reaches openlibrary.org when #13070 ships" not in live


def test_comment_is_marked_resolved_when_no_affected_edits_remain():
    body = render_comment([], in_place=True)
    assert body.startswith(MARKER)
    assert "Resolved" in body
    assert "messages.po`\n" not in body
