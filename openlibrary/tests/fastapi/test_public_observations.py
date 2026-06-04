"""Tests for GET /observations.json (FastAPI)."""

from unittest.mock import patch

import pytest

SAMPLE_METRICS = {
    "OL27482W": {
        "work_id": "27482",
        "total_respondents": 1,
        "observations": [
            {
                "label": "Impressions",
                "description": "How did you feel about this book and do you recommend it?",
                "multi_choice": True,
                "total_respondents_for_type": 1,
                "values": [{"value": "Recommend", "count": 1}],
                "total_responses": 1,
            }
        ],
    },
    "OL24204W": {"work_id": "24204", "total_respondents": 0, "observations": []},
}


@pytest.fixture
def mock_get_metrics():
    """Prevent real DB calls for get_observation_metrics."""
    with patch("openlibrary.fastapi.internal.api.get_observation_metrics", autospec=True) as mock:
        mock.side_effect = lambda olid: SAMPLE_METRICS.get(olid, {})
        yield mock


class TestPublicObservations:
    def test_no_olids_returns_empty(self, fastapi_client, mock_get_metrics):
        response = fastapi_client.get("/observations.json")
        assert response.json() == {"observations": {}}
        mock_get_metrics.assert_not_called()

    def test_single_olid(self, fastapi_client, mock_get_metrics):
        response = fastapi_client.get("/observations.json?olid=OL27482W")
        data = response.json()
        assert data["observations"]["OL27482W"] == SAMPLE_METRICS["OL27482W"]
        mock_get_metrics.assert_called_once_with("OL27482W")

    def test_multiple_olids(self, fastapi_client, mock_get_metrics):
        response = fastapi_client.get("/observations.json?olid=OL27482W&olid=OL24204W")
        observations = response.json()["observations"]
        assert observations["OL27482W"] == SAMPLE_METRICS["OL27482W"]
        assert observations["OL24204W"] == SAMPLE_METRICS["OL24204W"]
        assert mock_get_metrics.call_count == 2
