import subprocess
from types import SimpleNamespace

import pytest

from openlibrary.utils import template_usage


def _git_result(*paths: str) -> SimpleNamespace:
    return SimpleNamespace(stdout=("\0".join(paths) + "\0").encode())


def test_build_corpus_uses_git_tracked_infogami_files(tmp_path, monkeypatch):
    source = tmp_path / "vendor" / "infogami" / "infogami" / "core" / "code.py"
    source.parent.mkdir(parents=True)
    source.write_text("render.viewpage()")
    monkeypatch.setattr(template_usage, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: _git_result("vendor/infogami/infogami/core/code.py"),
    )

    assert template_usage.build_corpus() == {"vendor/infogami/infogami/core/code.py": "render.viewpage()"}


def test_build_corpus_falls_back_to_infogami_files_on_disk(tmp_path, monkeypatch):
    source = tmp_path / "vendor" / "infogami" / "infogami" / "core" / "code.py"
    source.parent.mkdir(parents=True)
    source.write_text("render.viewpage()")
    template = tmp_path / "vendor" / "infogami" / "templates" / "view.html"
    template.parent.mkdir(parents=True)
    template.write_text("$def with ()")
    (template.parent / "README.md").write_text("not part of the corpus")
    monkeypatch.setattr(template_usage, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: _git_result("openlibrary/code.py"))

    assert template_usage.build_corpus() == {
        "vendor/infogami/infogami/core/code.py": "render.viewpage()",
        "vendor/infogami/templates/view.html": "$def with ()",
    }


@pytest.mark.parametrize("create_empty_directory", [False, True])
def test_build_corpus_rejects_missing_or_empty_infogami_checkout(tmp_path, monkeypatch, create_empty_directory):
    if create_empty_directory:
        (tmp_path / "vendor" / "infogami").mkdir(parents=True)
    monkeypatch.setattr(template_usage, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: _git_result("openlibrary/code.py"))

    with pytest.raises(RuntimeError, match="no usable infogami checkout exists"):
        template_usage.build_corpus()
