from pathlib import Path

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


# #13070 at c3f58ba06: the olbase build runs a pull script instead of cloning inline.
OLBASE_13070_PULL_SCRIPT = (
    "COPY --chown=openlibrary:openlibrary . /openlibrary\n"
    "\n"
    "# Translations come from openlibrary-i18n at I18N_REF (a branch, tag or SHA). olbase.yaml\n"
    "# resolves it to one SHA so both architectures bake the same translations.\n"
    "ARG I18N_REF=main\n"
    "\n"
    "RUN ln -s vendor/infogami/infogami infogami \\\n"
    ' && ./scripts/i18n-pull-translations.sh "$I18N_REF" \\\n'
    " && make\n"
)


def test_overwrite_is_detected_from_13070s_pull_script():
    assert overwrite_in_place(OLBASE_13070_PULL_SCRIPT)


def test_a_comment_naming_the_clone_url_is_not_the_overwrite():
    text = "# see https://github.com/internetarchive/openlibrary-i18n\nRUN make\n"
    assert not overwrite_in_place(text)


# --- main(): finding, updating and resolving the one comment -----------------

import scripts.gh_scripts.po_edit_warning as pew


def _run_main(monkeypatch, tmp_path, *, files, comments):
    (tmp_path / "docker").mkdir()
    (tmp_path / "docker" / "Dockerfile.olbase").write_text("RUN make\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setenv("GITHUB_REPOSITORY", "internetarchive/openlibrary")
    monkeypatch.setenv("PR_NUMBER", "1")
    writes = []

    def fake(method, url, token, body=None):
        if method != "GET":
            writes.append((method, url, body["body"]))
            return {}, ""
        if "/pulls/1/files" in url:
            return [{"filename": f} for f in files], ""
        if "/contents/locale" in url:
            return [{"name": lang, "type": "dir"} for lang in sorted(I18N)], ""
        if "/issues/1/comments" in url:
            return comments, ""
        raise AssertionError(url)

    monkeypatch.setattr(pew, "_request", fake)
    assert pew.main() == 0
    return writes


def _comment(body, login="github-actions[bot]", type_="Bot", id_=7):
    return {"body": body, "user": {"login": login, "type": type_}, "url": f"https://api.github.com/c/{id_}"}


ES = ["openlibrary/i18n/es/messages.po"]


def test_main_posts_one_comment_for_an_affected_edit(monkeypatch, tmp_path):
    writes = _run_main(monkeypatch, tmp_path, files=ES, comments=[])
    assert [(m, u.rsplit("/", 2)[-2:]) for m, u, _ in writes] == [("POST", ["1", "comments"])]


def test_main_updates_its_own_comment_instead_of_adding_another(monkeypatch, tmp_path):
    ours = _comment(MARKER + "\nstale")
    writes = _run_main(monkeypatch, tmp_path, files=ES, comments=[ours])
    assert [(m, u) for m, u, _ in writes] == [("PATCH", ours["url"])]


def test_main_leaves_a_current_comment_alone(monkeypatch, tmp_path):
    ours = _comment(render_comment(["es"], in_place=False))
    assert _run_main(monkeypatch, tmp_path, files=ES, comments=[ours]) == []


def test_main_resolves_its_comment_when_the_edits_are_removed(monkeypatch, tmp_path):
    ours = _comment(MARKER + "\nold warning")
    writes = _run_main(monkeypatch, tmp_path, files=["README.md"], comments=[ours])
    assert [m for m, _, _ in writes] == ["PATCH"]
    assert "Resolved" in writes[0][2]


def test_main_ignores_marker_comments_it_did_not_write(monkeypatch, tmp_path):
    human = _comment(MARKER + "\nhuman", login="someone", type_="User", id_=1)
    other_bot = _comment(MARKER + "\nother bot", login="claude[bot]", id_=2)
    writes = _run_main(monkeypatch, tmp_path, files=ES, comments=[human, other_bot])
    assert [m for m, _, _ in writes] == ["POST"]


def _detector_covers(dockerfile_text):
    """True unless the Dockerfile's code mentions i18n in a way overwrite_in_place misses."""
    code = "\n".join(line for line in dockerfile_text.splitlines() if not line.lstrip().startswith("#"))
    return "i18n" not in code.lower() or overwrite_in_place(dockerfile_text)


def test_the_detector_recognises_whatever_the_real_dockerfile_does_with_i18n():
    # Fails in the CI of any PR (e.g. a rebased #13070) that pulls translations into olbase
    # in a form overwrite_in_place does not recognise, instead of silently leaving the
    # warning's wording stuck on "Once #13070 lands".
    assert _detector_covers(Path("docker/Dockerfile.olbase").read_text())


def test_the_drift_guard_fires_on_an_unrecognised_form():
    assert not _detector_covers("RUN ./scripts/fetch-translations-i18n.sh main && make\n")
    assert _detector_covers(OLBASE_13070_PULL_SCRIPT)
