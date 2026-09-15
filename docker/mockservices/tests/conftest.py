"""Make the repo root importable for the tests in this directory.

These tests import ``openlibrary.core.matomo`` to exercise the mock Matomo feed
over real HTTP. That works inside the dev containers only because
the image sets ``PYTHONPATH=/openlibrary``; GitHub CI sets no such thing.

pytest's default ``prepend`` import mode inserts a test module's *basedir* onto
``sys.path`` -- the first ancestor directory without an ``__init__.py``. For
tests under ``openlibrary/tests/`` that walk lands on the repo root, so
``openlibrary`` imports fine. This directory has no ``__init__.py`` chain, so the
basedir is this directory, and ``import openlibrary`` fails at collection with
``ModuleNotFoundError`` -- which is exactly how CI broke.

Adding ``__init__.py`` files here would be the other fix, but ``main.py`` and
``requirements.txt`` in this tree are copied into the mockservices container as
flat files (see ``docker/mockservices/Dockerfile``), and turning it into a
package for the benefit of the test runner would misrepresent what it is.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parents[3]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
