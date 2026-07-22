from infogami import config
from openlibrary import config as ol_config


class TestApplyInfobaseServerOverride:
    def test_overrides_when_env_var_set(self, monkeypatch):
        monkeypatch.setenv("INFOBASE_SERVER_OVERRIDE", "infobase:7000")
        monkeypatch.setattr(config, "infobase_server", "ol-home:7000", raising=False)
        ol_config._apply_infobase_server_override()
        assert config.infobase_server == "infobase:7000"

    def test_logs_when_override_applies(self, monkeypatch, caplog):
        monkeypatch.setenv("INFOBASE_SERVER_OVERRIDE", "infobase:7000")
        monkeypatch.setattr(config, "infobase_server", "ol-home:7000", raising=False)
        with caplog.at_level("INFO", logger="openlibrary.config"):
            ol_config._apply_infobase_server_override()
        assert "infobase:7000" in caplog.text

    def test_no_override_when_env_var_unset(self, monkeypatch):
        monkeypatch.delenv("INFOBASE_SERVER_OVERRIDE", raising=False)
        monkeypatch.setattr(config, "infobase_server", "ol-home:7000", raising=False)
        ol_config._apply_infobase_server_override()
        assert config.infobase_server == "ol-home:7000"

    def test_no_log_when_env_var_unset(self, monkeypatch, caplog):
        monkeypatch.delenv("INFOBASE_SERVER_OVERRIDE", raising=False)
        monkeypatch.setattr(config, "infobase_server", "ol-home:7000", raising=False)
        with caplog.at_level("INFO", logger="openlibrary.config"):
            ol_config._apply_infobase_server_override()
        assert caplog.text == ""

    def test_no_override_when_env_var_empty_string(self, monkeypatch):
        monkeypatch.setenv("INFOBASE_SERVER_OVERRIDE", "")
        monkeypatch.setattr(config, "infobase_server", "ol-home:7000", raising=False)
        ol_config._apply_infobase_server_override()
        assert config.infobase_server == "ol-home:7000"

    def test_noop_when_no_infobase_server_configured(self, monkeypatch):
        monkeypatch.setenv("INFOBASE_SERVER_OVERRIDE", "infobase:7000")
        monkeypatch.delattr(config, "infobase_server", raising=False)
        ol_config._apply_infobase_server_override()
        assert config.get("infobase_server") is None
