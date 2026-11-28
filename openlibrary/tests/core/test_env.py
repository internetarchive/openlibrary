import pytest
import web

from openlibrary.core.env import get_deployment_name


def test_deployment_name_defaults_to_development_without_context(monkeypatch):
    monkeypatch.delenv("OL_DEPLOYMENT_NAME", raising=False)
    monkeypatch.delattr(web.ctx, "host", raising=False)

    assert get_deployment_name() == "development"


def test_deployment_name_prefers_environment(monkeypatch):
    monkeypatch.setenv("OL_DEPLOYMENT_NAME", "testing")
    monkeypatch.setattr(web.ctx, "host", "openlibrary.org", raising=False)

    assert get_deployment_name() == "testing"


def test_deployment_name_rejects_invalid_environment_value(monkeypatch):
    monkeypatch.setenv("OL_DEPLOYMENT_NAME", "staging")

    with pytest.raises(ValueError, match="Invalid OL_DEPLOYMENT_NAME"):
        get_deployment_name()


def test_deployment_name_uses_request_host_without_environment(monkeypatch):
    monkeypatch.delenv("OL_DEPLOYMENT_NAME", raising=False)
    monkeypatch.setattr(web.ctx, "host", "www.openlibrary.org", raising=False)

    assert get_deployment_name() == "production"


def test_deployment_name_uses_testing_host_without_environment(monkeypatch):
    monkeypatch.delenv("OL_DEPLOYMENT_NAME", raising=False)
    monkeypatch.setattr(web.ctx, "host", "testing.openlibrary.org", raising=False)

    assert get_deployment_name() == "testing"
