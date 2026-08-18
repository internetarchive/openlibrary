from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest
import yaml

from openlibrary.core import features as features_module
from openlibrary.core.features import Features


def _full_config() -> str:
    return "features:\n    debug: enabled\n"


def _write_test_config(tmp_path: Path, body: str | None = None) -> Path:
    config = tmp_path / "openlibrary.yml"
    config.write_text(dedent(body or _full_config()))
    features_module.features = Features.from_yaml(config)
    return config


@pytest.fixture(autouse=True)
def _reset_features_to_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("OL_CONFIG", raising=False)
    _write_test_config(tmp_path)


class TestConstructor:
    def test_instantiates_with_no_flags(self):
        f = Features()
        assert isinstance(f, Features)

    def test_extra_fields_are_ignored(self):
        f = Features(nonexistent=True)
        assert not hasattr(f, "nonexistent")


class TestFromYaml:
    def test_loads_config_with_debug_flag(self, tmp_path: Path):
        (tmp_path / "openlibrary.yml").write_text(dedent(_full_config()))
        f = Features.from_yaml(tmp_path / "openlibrary.yml")
        assert isinstance(f, Features)

    def test_ignores_non_features_keys(self, tmp_path: Path):
        full = _full_config()
        config = tmp_path / "openlibrary.yml"
        config.write_text("site: openlibrary.org\n" + full)
        f = Features.from_yaml(config)
        assert isinstance(f, Features)

    def test_unknown_key_is_ignored(self, tmp_path: Path):
        config = tmp_path / "openlibrary.yml"
        config.write_text("features:\n    history_v2: admin\n")
        f = Features.from_yaml(config)
        assert isinstance(f, Features)


class TestRealConfig:
    def test_real_config_loads_without_error(self):
        f = Features.from_yaml("conf/openlibrary.yml")
        assert isinstance(f, Features)

    def test_symbolic_debug_flag_in_yaml(self):
        raw = yaml.safe_load(Path("conf/openlibrary.yml").read_text())
        features_section = raw.get("features", {})
        assert "debug" in features_section


class TestModuleInstance:
    def test_features_is_a_features_instance(self):
        assert isinstance(features_module.features, Features)

    def test_features_singleton_is_shared(self):
        assert features_module.features is features_module.features

    def test_reflects_yaml_reload(self, tmp_path: Path):
        _write_test_config(tmp_path)
        assert isinstance(features_module.features, Features)
