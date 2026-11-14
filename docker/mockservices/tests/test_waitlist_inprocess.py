import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

MOCKSERVICES_MAIN = Path(__file__).parents[1] / "main.py"


def _load_mock_app():
    spec = importlib.util.spec_from_file_location("ol_mockservices_waitlist_main", MOCKSERVICES_MAIN)
    if spec is None or spec.loader is None:
        pytest.fail(f"could not load {MOCKSERVICES_MAIN}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.app


@pytest.fixture(scope="module")
def client():
    return TestClient(_load_mock_app())


def _query(client, identifier=None, userid=None):
    payload = {"method": "waitinglist.query"}
    if identifier is not None:
        payload["identifier"] = identifier
    if userid is not None:
        payload["userid"] = userid

    response = client.post("/services/loans/loan/", json=payload)
    assert response.status_code == 200
    return response.json()["result"]


def test_s3_join_and_leave_waitlist(client):
    identifier = f"waitlist-action-{uuid4().hex}"

    join_response = client.post(
        "/services/loans/loan/",
        params={"action": "join_waitlist", "identifier": identifier},
        data={"access": "foo", "secret": "foo"},
    )
    assert join_response.status_code == 200
    assert join_response.json() == {"status": "ok"}

    records = _query(client, identifier, "@openlibrary")
    assert len(records) == 1
    assert records[0]["identifier"] == identifier
    assert records[0]["userid"] == "@openlibrary"
    assert records[0]["status"] == "waiting"
    assert records[0]["since"]
    assert records[0]["position"] == 1
    assert records[0]["wl_size"] == 1

    leave_response = client.post(
        "/services/loans/loan/",
        params={"action": "leave_waitlist", "identifier": identifier},
        data={"access": "foo", "secret": "foo"},
    )
    assert leave_response.status_code == 200
    assert leave_response.json() == {"status": "ok"}
    assert _query(client, identifier, "@openlibrary") == []


def test_waitlist_method_queries_preserve_fifo_and_exact_user_ids(client):
    identifier = f"waitlist-method-{uuid4().hex}"
    first_user = "@waitlist_first"
    second_user = "@waitlist_second"

    for userid in (first_user, second_user):
        response = client.post(
            "/services/loans/loan/",
            json={
                "method": "waitinglist.join",
                "identifier": identifier,
                "userid": userid,
            },
        )
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    records = _query(client, identifier)
    assert [record["userid"] for record in records] == [first_user, second_user]
    assert [record["position"] for record in records] == [1, 2]
    assert [record["wl_size"] for record in records] == [2, 2]

    second_user_record = _query(client, identifier, second_user)
    assert len(second_user_record) == 1
    assert second_user_record[0]["position"] == 2
    assert second_user_record[0]["wl_size"] == 2

    assert _query(client, identifier, "ol:waitlist_second") == []

    leave_response = client.post(
        "/services/loans/loan/",
        json={
            "method": "waitinglist.leave",
            "identifier": identifier,
            "userid": first_user,
        },
    )
    assert leave_response.status_code == 200
    assert leave_response.json() == {"status": "ok"}

    remaining = _query(client, identifier)
    assert len(remaining) == 1
    assert remaining[0]["userid"] == second_user
    assert remaining[0]["position"] == 1
    assert remaining[0]["wl_size"] == 1


def test_duplicate_join_keeps_place_and_rejoining_after_leave_goes_to_back(client):
    identifier = f"waitlist-duplicate-{uuid4().hex}"
    first_user = "@waitlist_first"
    second_user = "@waitlist_second"

    def join(userid):
        return client.post(
            "/services/loans/loan/",
            json={
                "method": "waitinglist.join",
                "identifier": identifier,
                "userid": userid,
            },
        )

    def leave(userid):
        return client.post(
            "/services/loans/loan/",
            json={
                "method": "waitinglist.leave",
                "identifier": identifier,
                "userid": userid,
            },
        )

    assert join(first_user).status_code == 200
    assert join(second_user).status_code == 200

    # Rejoining while still queued will not create a duplicate or move the patron.
    assert join(first_user).status_code == 200

    records = _query(client, identifier)
    assert [record["userid"] for record in records] == [first_user, second_user]
    assert [record["position"] for record in records] == [1, 2]
    assert [record["wl_size"] for record in records] == [2, 2]

    # Leaving removes the first patron. Joining again places them after the second.
    assert leave(first_user).status_code == 200
    assert join(first_user).status_code == 200

    records = _query(client, identifier)
    assert [record["userid"] for record in records] == [second_user, first_user]
    assert [record["position"] for record in records] == [1, 2]
    assert [record["wl_size"] for record in records] == [2, 2]


def test_waitlist_query_by_user_returns_all_books_without_duplicates(client):
    userid = "@waitlist_account"
    identifiers = [
        f"waitlist-account-a-{uuid4().hex}",
        f"waitlist-account-b-{uuid4().hex}",
    ]

    for identifier in identifiers:
        response = client.post(
            "/services/loans/loan/",
            json={
                "method": "waitinglist.join",
                "identifier": identifier,
                "userid": userid,
            },
        )
        assert response.status_code == 200

    itemname_results = _query(client, userid=userid)
    ol_userid_results = _query(client, userid="ol:waitlist_account")

    assert {record["identifier"] for record in itemname_results} == set(identifiers)
    assert all(record["userid"] == userid for record in itemname_results)
    assert ol_userid_results == []
