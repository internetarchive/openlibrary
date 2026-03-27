"""Tests for GET /observations.json (FastAPI)."""

from unittest.mock import patch

import pytest


@pytest.fixture
def mock_get_metrics():
    """Prevent real DB calls for get_observation_metrics."""
    with patch("openlibrary.fastapi.internal.api.get_observation_metrics", autospec=True) as mock:
        def mock_metrics_return(olid):
            if olid == "OL27482W":
                return {
                    "work_id": "27482",
                    "total_respondents": 1,
                    "observations": [
                        {
                            "label": "Impressions",
                            "description": "How did you feel about this book and do you recommend it?",
                            "multi_choice": True,
                            "total_respondents_for_type": 1,
                            "values": [{"value": "Recommend", "count": 1}],
                            "total_responses": 1
                        }
                    ]
                }
            elif olid == "OL24204W":
                return {
                    "work_id": "24204",
                    "total_respondents": 0,
                    "observations": []
                }
            elif olid == "hehe":
                raise Exception("Backend crash due to invalid OLID")
            return {}

        mock.side_effect = mock_metrics_return
        yield mock


class TestPublicObservations:
    """Tests for GET /observations.json."""

    def test_empty_request(self, fastapi_client, mock_get_metrics):
        """Requesting without OLIDs returns an empty dictionary without calling DB."""
        response = fastapi_client.get("/observations.json")
        assert response.status_code == 200
        assert response.json() == {"observations": {}}
        mock_get_metrics.assert_not_called()

    def test_single_olid(self, fastapi_client, mock_get_metrics):
        """Requesting with a single OLID returns the correct metrics."""
        response = fastapi_client.get("/observations.json?olid=OL27482W")
        assert response.status_code == 200
        data = response.json()
        assert "OL27482W" in data["observations"]
        assert data["observations"]["OL27482W"]["total_respondents"] == 1
        mock_get_metrics.assert_called_once_with("OL27482W")

    def test_multiple_olids(self, fastapi_client, mock_get_metrics):
        """Requesting with multiple OLIDs returns the correct metrics for each."""
        response = fastapi_client.get("/observations.json?olid=OL27482W&olid=OL24204W")
        assert response.status_code == 200
        data = response.json()
        assert "observations" in data
        sample_data = data["observations"]["OL27482W"]
        assert sample_data["work_id"] == "27482"
        assert sample_data["total_respondents"] == 1
        assert len(sample_data["observations"]) == 1
        assert sample_data["observations"][0]["label"] == "Impressions"
        assert sample_data["observations"][0]["values"][0]["value"] == "Recommend"
        empty_book_data = data["observations"]["OL24204W"]
        assert empty_book_data["work_id"] == "24204"
        assert empty_book_data["total_respondents"] == 0
        assert len(empty_book_data["observations"]) == 0
        assert mock_get_metrics.call_count == 2
        mock_get_metrics.assert_any_call("OL27482W")
        mock_get_metrics.assert_any_call("OL24204W")

    def test_invalid_olid_raises_500(self, fastapi_client, mock_get_metrics):
        """Invalid OLID that causes the backend to crash should propagate the Exception."""
        with pytest.raises(Exception, match="Backend crash due to invalid OLID"):
            fastapi_client.get("/observations.json?olid=hehe")
        mock_get_metrics.assert_called_once_with("hehe")
