from openlibrary.core.experiments import ACTIVE_EXPERIMENTS, get_user_experiments, get_variant


def test_get_variant_fallback():
    # Empty or None user identifier should fall back to control
    assert get_variant("AB_Testing", "") == "control"
    assert get_variant("AB_Testing", None) == "control"  # type: ignore[arg-type]

    # Non-existent experiment should fall back to control
    assert get_variant("Non_Existent", "user123") == "control"


def test_get_variant_distribution():
    # Evaluate distribution across a reasonable number of users
    variants_seen = set()
    for i in range(100):
        variant = get_variant("AB_Testing", f"user_{i}")
        assert variant in ACTIVE_EXPERIMENTS["AB_Testing"]
        variants_seen.add(variant)

    # Ensure all variants are allocated at least once (probabilistically guaranteed for N=100)
    assert len(variants_seen) > 1
    assert "control" in variants_seen
    assert "a" in variants_seen
    assert "b" in variants_seen


def test_get_user_experiments():
    experiments = get_user_experiments("user_456")
    assert "AB_Testing" in experiments
    assert experiments["AB_Testing"] in ACTIVE_EXPERIMENTS["AB_Testing"]


def test_get_user_experiments_overrides():
    # Valid override should change the variant
    overrides = {"experiment_AB_Testing": "b"}
    experiments = get_user_experiments("user_456", overrides=overrides)
    assert experiments["AB_Testing"] == "b"

    # Invalid override group/variant should be ignored
    overrides = {"experiment_AB_Testing": "invalid_group"}
    experiments = get_user_experiments("user_456", overrides=overrides)
    assert experiments["AB_Testing"] != "invalid_group"
    assert experiments["AB_Testing"] in ACTIVE_EXPERIMENTS["AB_Testing"]

    # Invalid override key/name format should be ignored
    overrides = {"AB_Testing": "b"}
    experiments = get_user_experiments("user_456", overrides=overrides)
    assert experiments["AB_Testing"] in ACTIVE_EXPERIMENTS["AB_Testing"]
