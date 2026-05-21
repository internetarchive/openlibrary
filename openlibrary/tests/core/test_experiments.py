from openlibrary.core.experiments import ACTIVE_EXPERIMENTS, get_user_experiments, get_variant


def test_get_variant_fallback():
    # Empty or None user identifier should fall back to control
    assert get_variant("AB_Testing", "") == "control"
    assert get_variant("AB_Testing", None) == "control"

    # Non-existent experiment should fall back to control
    assert get_variant("Non_Existent", "user123") == "control"


def test_get_variant_distribution():
    # Evaluate distribution across a reasonable number of users
    variants_seen = set()
    for i in range(100):
        variant = get_variant("AB_Testing", f"user_{i}")
        assert variant in ACTIVE_EXPERIMENTS["AB_Testing"]["variants"]
        variants_seen.add(variant)

    # Ensure all variants are allocated at least once (probabilistically guaranteed for N=100)
    assert len(variants_seen) > 1
    assert "control" in variants_seen
    assert "a" in variants_seen
    assert "b" in variants_seen


def test_get_user_experiments():
    experiments = get_user_experiments("user_456")
    assert "AB_Testing" in experiments
    assert experiments["AB_Testing"] in ACTIVE_EXPERIMENTS["AB_Testing"]["variants"]


def test_get_user_experiments_overrides():
    # Valid override should change the variant
    overrides = {"experiment_AB_Testing": "b"}
    experiments = get_user_experiments("user_456", overrides=overrides)
    assert experiments["AB_Testing"] == "b"

    # Invalid override group/variant should be ignored
    overrides = {"experiment_AB_Testing": "invalid_group"}
    experiments = get_user_experiments("user_456", overrides=overrides)
    assert experiments["AB_Testing"] != "invalid_group"
    assert experiments["AB_Testing"] in ACTIVE_EXPERIMENTS["AB_Testing"]["variants"]

    # Invalid override key/name format should be ignored
    overrides = {"AB_Testing": "b"}
    experiments = get_user_experiments("user_456", overrides=overrides)
    assert experiments["AB_Testing"] in ACTIVE_EXPERIMENTS["AB_Testing"]["variants"]


def test_authorized_only_experiment():
    ACTIVE_EXPERIMENTS["Auth_Only_Testing"] = {
        "variants": {
            "control": 25,
            "treatment": 75,
        },
        "authorized_only": True,
    }
    try:
        # If not logged in, should always fall back to control
        for i in range(100):
            assert get_variant("Auth_Only_Testing", f"user_{i}", is_logged_in=False) == "control"

        # If logged in, should distribute into variants
        variants_seen = set()
        for i in range(100):
            variant = get_variant("Auth_Only_Testing", f"user_{i}", is_logged_in=True)
            assert variant in ["control", "treatment"]
            variants_seen.add(variant)

        assert len(variants_seen) > 1
    finally:
        ACTIVE_EXPERIMENTS.pop("Auth_Only_Testing", None)


def test_get_user_experiments_authorized_only():
    ACTIVE_EXPERIMENTS["Auth_Only_Testing"] = {
        "variants": {
            "control": 25,
            "treatment": 75,
        },
        "authorized_only": True,
    }
    try:
        # If not logged in, should get control
        experiments = get_user_experiments("user_456", is_logged_in=False)
        assert experiments["Auth_Only_Testing"] == "control"

        # If logged in, should evaluate variant
        experiments_logged_in = get_user_experiments("user_456", is_logged_in=True)
        assert experiments_logged_in["Auth_Only_Testing"] in ["control", "treatment"]
    finally:
        ACTIVE_EXPERIMENTS.pop("Auth_Only_Testing", None)
