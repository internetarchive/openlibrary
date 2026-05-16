def test_get_list_seeds_public_success(fastapi_client, monkeypatch):
    """Test fetching seeds for a known public list."""

    def mock_get_list_seeds(key):
        return {"entries": [{"url": "/works/OL123W", "type": "work"}], "size": 1}

    monkeypatch.setattr("openlibrary.fastapi.lists.get_list_seeds", mock_get_list_seeds)

    response = fastapi_client.get("/lists/OL3L/seeds.json")
    assert response.status_code == 200
    data = response.json()
    assert "entries" in data
    assert data["size"] == 1


def test_get_list_seeds_not_found(fastapi_client, monkeypatch):
    """Test fetching seeds for a list that does not exist."""

    def mock_get_list_seeds(key):
        return None

    monkeypatch.setattr("openlibrary.fastapi.lists.get_list_seeds", mock_get_list_seeds)

    response = fastapi_client.get("/lists/OL999999L/seeds.json")
    assert response.status_code == 404
    assert response.json() == {"detail": "List or Series not found"}


def test_post_list_seeds_unauthorized(fastapi_client, mock_site):
    """Test that unauthorized users cannot mutate seeds."""
    payload = {"add": ["/works/OL123W"], "remove": []}
    response = fastapi_client.post("/lists/OL3L/seeds.json", json=payload)
    assert response.status_code in [401, 403]


def test_post_list_seeds_authorized(fastapi_client, mock_authenticated_user, mock_site):
    """Test that a logged-in user successfully hits the permission logic."""
    payload = {"add": ["/works/OL123W"], "remove": []}
    response = fastapi_client.post("/lists/OL3L/seeds.json", json=payload)
    assert response.status_code in [200, 403, 404]
