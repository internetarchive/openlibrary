from datetime import UTC, datetime

import pytest
from babel.messages.pofile import read_po, write_po

from openlibrary import i18n


@pytest.fixture
def extract_env(monkeypatch, tmp_path):
    """Isolated directory for extract_messages tests.

    Creates empty openlibrary/templates/ and openlibrary/macros/ under tmp_path
    and chdirs there so the pinned paths in extract_messages resolve to those
    empty dirs instead of the real source tree.
    """
    (tmp_path / "openlibrary" / "templates").mkdir(parents=True)
    (tmp_path / "openlibrary" / "macros").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(i18n, "root", str(tmp_path))
    return tmp_path


def _stamp_old_date(pot_path):
    """Overwrite creation_date in an existing POT file with a known old date."""
    known_old = datetime(2020, 1, 1, tzinfo=UTC)
    with open(pot_path, "rb") as f:
        cat = read_po(f)
    cat.creation_date = known_old
    with open(pot_path, "wb") as f:
        write_po(f, cat, include_lineno=False)
    return known_old


def test_extract_messages_preserves_creation_date_when_unchanged(extract_env):
    tmp = extract_env
    src = tmp / "src"
    src.mkdir()
    (src / "views.py").write_text('_("test_unique_i18n_12463")\n')

    i18n.extract_messages([str(src)], verbose=False, skip_untracked=False)
    known_old = _stamp_old_date(tmp / "messages.pot")

    # Second run with identical source — date must be preserved
    i18n.extract_messages([str(src)], verbose=False, skip_untracked=False)

    with open(tmp / "messages.pot", "rb") as f:
        assert read_po(f).creation_date == known_old


def test_extract_messages_updates_creation_date_on_new_string(extract_env):
    tmp = extract_env
    src = tmp / "src"
    src.mkdir()
    src_file = src / "views.py"
    src_file.write_text('_("test_unique_i18n_12463")\n')

    i18n.extract_messages([str(src)], verbose=False, skip_untracked=False)
    known_old = _stamp_old_date(tmp / "messages.pot")

    # Add a new string — message set changes, so date must update
    src_file.write_text('_("test_unique_i18n_12463")\n_("test_unique_i18n_12463_new")\n')
    i18n.extract_messages([str(src)], verbose=False, skip_untracked=False)

    with open(tmp / "messages.pot", "rb") as f:
        assert read_po(f).creation_date != known_old


def test_extract_messages_handles_malformed_pot(extract_env):
    tmp = extract_env
    src = tmp / "src"
    src.mkdir()
    (src / "views.py").write_text('_("test_unique_i18n_12463")\n')

    # Write a corrupt POT file (e.g. git conflict markers)
    (tmp / "messages.pot").write_bytes(b"<<<<<<< HEAD\nmalformed content\n=======\n>>>>>>> branch\n")

    # Must not raise — falls back to regenerating with current timestamp
    i18n.extract_messages([str(src)], verbose=False, skip_untracked=False)

    with open(tmp / "messages.pot", "rb") as f:
        assert read_po(f).creation_date is not None
