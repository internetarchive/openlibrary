from unittest.mock import patch

import pytest

from openlibrary.plugins.worksearch.subjects import SubjectEngine


class TestFacetWrapper:
    def test_invalid_subject_facet_includes_value_in_error(self):
        engine = SubjectEngine(
            name="subject",
            key="subjects",
            prefix="/subjects/",
            facet="subject_facet",
            facet_key="subject_key",
        )
        with patch("openlibrary.plugins.worksearch.subjects.SUBJECTS", []), pytest.raises(AssertionError, match="subject_facet"):
            engine.facet_wrapper("subject_facet", "some_value", "Some Label", 5)
