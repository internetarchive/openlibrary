import json
import urllib.parse
import urllib.request

import pytest


class FeedbackAPI:
    def __init__(self, server, username=None, password=None):
        self.server = server
        self.username = username
        self.password = password
        self.opener = urllib.request.build_opener()

    def urlopen(self, path, data=None, method=None, headers=None):
        headers = headers or {}
        if not method:
            method = "POST" if data else "GET"

        if data and isinstance(data, dict):
            data = json.dumps(data).encode('utf-8')
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(self.server + path, data=data, headers=headers)
        req.get_method = lambda: method
        return self.opener.open(req)

    def submit_feedback(self, subject, comment):
        data = {"subject": subject, "comment": comment}
        response = self.urlopen("/feedback", data=data)
        return json.loads(response.read())


# Example test
# def test_feedback_submission(pytestconfig):
#     server = pytestconfig.getoption("server") or "http://localhost:8080"  # Fallback
#     api = FeedbackAPI(server)

#     result = api.submit_feedback("Test Subject", "This is a test comment")
#     assert result.get("success") is True


def test_feedback_submission(pytestconfig):
    server = pytestconfig.getoption("server")
    if not server:
        pytest.skip(
            "Skipping test: --server argument not provided (e.g., --server=http://web:8080)"
        )

    api = FeedbackAPI(server)
    result = api.submit_feedback("Test Subject", "This is a test comment")
    assert result.get("success") is True
