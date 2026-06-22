from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest
import yaml

from openlibrary.core import features as features_module
from openlibrary.core.features import Features


def _write_test_config(tmp_path: Path, body: str) -> Path:
    config = tmp_path / "openlibrary.yml"
    config.write_text(dedent(body))
    features_module.features = Features.from_yaml(config)
    return config


@pytest.fixture(autouse=True)
def _reset_features_to_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("OL_FEATURES_YAML_PATH", raising=False)
    _write_test_config(
        tmp_path,
        """\
        features:
            debug: false
            dev: false
            lists: true
            publishers: false
            recentchanges_v2: false
            stats: true
            stats-header: true
            superfast: false
            undo: true
        """,
    )


class TestDefaults:
    def test_default_values(self):
        f = Features()
        assert f.debug is False
        assert f.dev is False
        assert f.lists is True
        assert f.publishers is False
        assert f.recentchanges_v2 is False
        assert f.stats is True
        assert f.stats_header is True
        assert f.superfast is False
        assert f.undo is True

    def test_kwargs_override_defaults(self):
        f = Features(debug=True, lists=False)
        assert f.debug is True
        assert f.lists is False


class TestFromYaml:
    def test_loads_enabled_flags(self, tmp_path: Path):
        config = tmp_path / "openlibrary.yml"
        config.write_text(
            dedent(
                """\
                features:
                    stats: true
                    stats-header: true
                """
            )
        )
        f = Features.from_yaml(config)
        assert f.stats is True
        assert f.stats_header is True

    def test_unset_flags_use_defaults(self, tmp_path: Path):
        config = tmp_path / "openlibrary.yml"
        config.write_text("features:\n    stats: true\n")
        f = Features.from_yaml(config)
        assert f.stats is True
        assert f.stats_header is True  # default

    def test_ignores_non_features_keys(self, tmp_path: Path):
        config = tmp_path / "openlibrary.yml"
        config.write_text(
            dedent(
                """\
                site: openlibrary.org
                features:
                    stats: true
                """
            )
        )
        f = Features.from_yaml(config)
        assert f.stats is True
        assert "site" not in Features.model_fields

    def test_missing_features_section_uses_defaults(self, tmp_path: Path):
        config = tmp_path / "openlibrary.yml"
        config.write_text("site: openlibrary.org\n")
        f = Features.from_yaml(config)
        assert f.stats is True  # default
        assert f.stats_header is True  # default

    def test_kebab_case_normalized(self, tmp_path: Path):
        config = tmp_path / "openlibrary.yml"
        config.write_text("features:\n    stats-header: true\n")
        f = Features.from_yaml(config)
        assert f.stats_header is True

    def test_legacy_enabled_string(self, tmp_path: Path):
        config = tmp_path / "openlibrary.yml"
        config.write_text("features:\n    stats: enabled\n")
        f = Features.from_yaml(config)
        assert f.stats is True

    def test_legacy_disabled_string(self, tmp_path: Path):
        config = tmp_path / "openlibrary.yml"
        config.write_text("features:\n    stats: disabled\n")
        f = Features.from_yaml(config)
        assert f.stats is False

    def test_unrecognized_string_raises(self, tmp_path: Path):
        config = tmp_path / "openlibrary.yml"
        config.write_text("features:\n    stats: maybe\n")
        with pytest.raises(ValueError, match=r"Unrecognized feature flag value.*stats"):
            Features.from_yaml(config)

    def test_unknown_key_is_ignored(self, tmp_path: Path):
        config = tmp_path / "openlibrary.yml"
        config.write_text("features:\n    history_v2: admin\n    stats: true\n")
        f = Features.from_yaml(config)
        assert f.stats is True  # known fields unaffected
        # history_v2 is dropped — no group-gate support yet (Phase 3)


class TestRealConfig:
    def test_real_config_loads_without_error(self):
        f = Features.from_yaml("conf/openlibrary.yml")
        assert isinstance(f, Features)

    def test_real_config_stats_defaults_when_removed(self):
        """stats and stats-header are removed from YAML in Phase 1 —
        they use class defaults (True) which match legacy always-on behavior.
        """
        f = Features.from_yaml("conf/openlibrary.yml")
        assert f.stats is True
        assert f.stats_header is True

    def test_stats_and_stats_header_not_in_yaml(self):
        """Verify the flags are fully removed from config, not just renamed."""
        raw = yaml.safe_load(Path("conf/openlibrary.yml").read_text())
        features_section = raw.get("features", {})
        assert "stats" not in features_section
        assert "stats-header" not in features_section


class TestLegacyFlagMap:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("enabled", True),
            ("disabled", False),
            ("yes", True),
            ("no", False),
            ("true", True),
            ("false", False),
        ],
    )
    def test_all_legacy_strings(self, tmp_path: Path, raw: str, expected: bool):
        config = tmp_path / "openlibrary.yml"
        config.write_text(f"features:\n    stats: {raw}\n")
        f = Features.from_yaml(config)
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
        _write_test_config(tmp_path, "features:\n    stats: true\n    stats-header: true\n")
        assert features_module.features.stats is True
        assert features_module.features.stats_header is True
