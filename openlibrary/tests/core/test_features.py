from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest
import yaml
from pydantic import ValidationError

from openlibrary.core import features as features_module
from openlibrary.core.features import Features


def _full_config(**overrides: str) -> str:
    values = {
        "debug": "false",
        "dev": "false",
        "lists": "true",
        "publishers": "false",
        "recentchanges_v2": "false",
        "stats": "true",
        "stats-header": "true",
        "superfast": "false",
        "undo": "true",
    }
    values.update(overrides)
    lines = ["features:"]
    for key, value in values.items():
        lines.append(f"    {key}: {value}")
    return "\n".join(lines) + "\n"


def _write_test_config(tmp_path: Path, body: str | None = None) -> Path:
    config = tmp_path / "openlibrary.yml"
    config.write_text(dedent(body or _full_config()))
    features_module.features = Features.from_yaml(config)
    return config


@pytest.fixture(autouse=True)
def _reset_features_to_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("OL_FEATURES_YAML_PATH", raising=False)
    _write_test_config(tmp_path)


class TestConstructor:
    def test_requires_all_fields(self):
        with pytest.raises(ValidationError):
            Features()

    def test_kwargs_only(self):
        f = Features(
            debug=False,
            dev=False,
            lists=True,
            publishers=False,
            recentchanges_v2=False,
            stats=True,
            stats_header=True,
            superfast=False,
            undo=True,
        )
        assert f.stats is True

    def test_extra_fields_are_ignored(self):
        f = Features(
            debug=False,
            dev=False,
            lists=True,
            publishers=False,
            recentchanges_v2=False,
            stats=True,
            stats_header=True,
            superfast=False,
            undo=True,
            nonexistent=True,
        )
        assert f.stats is True
        assert not hasattr(f, "nonexistent")


class TestFromYaml:
    def test_loads_all_flags(self, tmp_path: Path):
        config = _full_config()
        (tmp_path / "openlibrary.yml").write_text(dedent(config))
        f = Features.from_yaml(tmp_path / "openlibrary.yml")
        assert f.stats is True
        assert f.stats_header is True
        assert f.debug is False
        assert f.undo is True

    def test_missing_field_raises(self, tmp_path: Path):
        config = tmp_path / "openlibrary.yml"
        config.write_text("features:\n    stats: true\n")
        with pytest.raises(ValidationError):
            Features.from_yaml(config)

    def test_missing_features_section_raises(self, tmp_path: Path):
        config = tmp_path / "openlibrary.yml"
        config.write_text("site: openlibrary.org\n")
        with pytest.raises(ValidationError):
            Features.from_yaml(config)

    def test_ignores_non_features_keys(self, tmp_path: Path):
        config = tmp_path / "openlibrary.yml"
        full = _full_config()
        config.write_text("site: openlibrary.org\n" + full)
        f = Features.from_yaml(config)
        assert f.stats is True
        assert "site" not in Features.model_fields

    def test_kebab_case_normalized(self, tmp_path: Path):
        config = _full_config(**{"stats-header": "false"})
        (tmp_path / "openlibrary.yml").write_text(dedent(config))
        f = Features.from_yaml(tmp_path / "openlibrary.yml")
        assert f.stats_header is False

    def test_legacy_enabled_string(self, tmp_path: Path):
        config = _full_config(stats="enabled")
        (tmp_path / "openlibrary.yml").write_text(dedent(config))
        f = Features.from_yaml(tmp_path / "openlibrary.yml")
        assert f.stats is True

    def test_legacy_disabled_string(self, tmp_path: Path):
        config = _full_config(stats="disabled")
        (tmp_path / "openlibrary.yml").write_text(dedent(config))
        f = Features.from_yaml(tmp_path / "openlibrary.yml")
        assert f.stats is False

    def test_unrecognized_string_raises(self, tmp_path: Path):
        config = _full_config(stats="maybe")
        (tmp_path / "openlibrary.yml").write_text(dedent(config))
        with pytest.raises(ValueError, match=r"Unrecognized feature flag value.*stats"):
            Features.from_yaml(tmp_path / "openlibrary.yml")

    def test_native_boolean(self, tmp_path: Path):
        config = _full_config(stats="false", **{"stats-header": "false"})
        (tmp_path / "openlibrary.yml").write_text(dedent(config))
        f = Features.from_yaml(tmp_path / "openlibrary.yml")
        assert f.stats is False
        assert f.stats_header is False

    def test_unknown_key_is_ignored(self, tmp_path: Path):
        config = tmp_path / "openlibrary.yml"
        full = _full_config()
        config.write_text("features:\n    history_v2: admin\n" + full[len("features:\n") :])
        f = Features.from_yaml(config)
        assert f.stats is True


class TestRealConfig:
    def test_real_config_loads_without_error(self):
        f = Features.from_yaml("conf/openlibrary.yml")
        assert isinstance(f, Features)

    def test_real_config_has_stats(self):
        f = Features.from_yaml("conf/openlibrary.yml")
        assert f.stats is True
        assert f.stats_header is True

    def test_stats_and_stats_header_in_yaml(self):
        raw = yaml.safe_load(Path("conf/openlibrary.yml").read_text())
        features_section = raw.get("features", {})
        assert "stats" in features_section
        assert "stats-header" in features_section


class TestLegacyFlagMap:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("enabled", True),
            ("disabled", False),
        ],
    )
    def test_legacy_strings(self, tmp_path: Path, raw: str, expected: bool):
        config = _full_config(stats=raw)
        (tmp_path / "openlibrary.yml").write_text(dedent(config))
        f = Features.from_yaml(tmp_path / "openlibrary.yml")
        assert f.stats is expected, f"expected {raw!r} -> {expected}, got {f.stats}"


class TestModuleInstance:
    def test_features_is_a_features_instance(self):
        assert isinstance(features_module.features, Features)

    def test_features_singleton_is_shared(self):
        assert features_module.features is features_module.features

    def test_dot_notation(self):
        assert features_module.features.stats is True
        assert features_module.features.stats_header is True

    def test_reflects_yaml_reload(self, tmp_path: Path):
        _write_test_config(tmp_path, _full_config(stats="false", **{"stats-header": "false"}))
        assert features_module.features.stats is False
        assert features_module.features.stats_header is False
