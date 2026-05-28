from openlibrary.core.experiments import ACTIVE_EXPERIMENTS, Audience, get_user_experiments, get_variant


def test_get_variant_fallback():
    # Empty or None user identifier should fall back to control
    assert get_variant("Sample_Experiment_1", "") == "control"
    assert get_variant("Sample_Experiment_1", None) == "control"

    # Non-existent experiment should fall back to control
    assert get_variant("Non_Existent", "user123") == "control"


def test_get_variant_distribution():
    # Set up a test experiment
    ACTIVE_EXPERIMENTS["Test_Distribution"] = {
        "variants": {
            "control": 30,
            "a": 35,
            "b": 35,
        },
        "audience": Audience.ALL,
    }
    try:
        variants_seen = set()
        for i in range(100):
            variant = get_variant("Test_Distribution", f"user_{i}")
            assert variant in ACTIVE_EXPERIMENTS["Test_Distribution"]["variants"]
            variants_seen.add(variant)

        # Ensure all variants are allocated at least once (probabilistically guaranteed for N=100)
        assert len(variants_seen) > 1
        assert "control" in variants_seen
        assert "a" in variants_seen
        assert "b" in variants_seen
    finally:
        ACTIVE_EXPERIMENTS.pop("Test_Distribution", None)


def test_get_user_experiments():
    ACTIVE_EXPERIMENTS["Test_User_Exp"] = {
        "variants": {
            "control": 50,
            "treatment": 50,
        },
        "audience": Audience.ALL,
    }
    try:
        experiments = get_user_experiments("user_456")
        assert "Test_User_Exp" in experiments
        assert experiments["Test_User_Exp"] in ACTIVE_EXPERIMENTS["Test_User_Exp"]["variants"]
    finally:
        ACTIVE_EXPERIMENTS.pop("Test_User_Exp", None)


def test_get_user_experiments_overrides():
    ACTIVE_EXPERIMENTS["Test_Overrides"] = {
        "variants": {
            "control": 50,
            "treatment": 50,
        },
        "audience": Audience.ALL,
    }
    try:
        # Valid override should change the variant
        overrides = {"experiment_Test_Overrides": "treatment"}
        experiments = get_user_experiments("user_456", overrides=overrides)
        assert experiments["Test_Overrides"] == "treatment"

        # Invalid override group/variant should be ignored
        overrides = {"experiment_Test_Overrides": "invalid_group"}
        experiments = get_user_experiments("user_456", overrides=overrides)
        assert experiments["Test_Overrides"] != "invalid_group"
        assert experiments["Test_Overrides"] in ACTIVE_EXPERIMENTS["Test_Overrides"]["variants"]

        # Invalid override key/name format should be ignored
        overrides = {"Test_Overrides": "treatment"}
        experiments = get_user_experiments("user_456", overrides=overrides)
        assert experiments["Test_Overrides"] in ACTIVE_EXPERIMENTS["Test_Overrides"]["variants"]
    finally:
        ACTIVE_EXPERIMENTS.pop("Test_Overrides", None)


def test_audience_targeting_logged_in():
    ACTIVE_EXPERIMENTS["Test_Logged_In"] = {
        "variants": {
            "control": 20,
            "treatment": 80,
        },
        "audience": Audience.LOGGED_IN,
    }
    try:
        # If not logged in, should always fall back to control
        for i in range(100):
            assert get_variant("Test_Logged_In", f"user_{i}", is_logged_in=False) == "control"

        # If logged in, should distribute into variants
        variants_seen = set()
        for i in range(100):
            variant = get_variant("Test_Logged_In", f"user_{i}", is_logged_in=True)
            assert variant in ["control", "treatment"]
            variants_seen.add(variant)

        assert len(variants_seen) > 1
    finally:
        ACTIVE_EXPERIMENTS.pop("Test_Logged_In", None)


def test_audience_targeting_logged_out():
    ACTIVE_EXPERIMENTS["Test_Logged_Out"] = {
        "variants": {
            "control": 20,
            "treatment": 80,
        },
        "audience": Audience.LOGGED_OUT,
    }
    try:
        # If logged in, should always fall back to control
        for i in range(100):
            assert get_variant("Test_Logged_Out", f"user_{i}", is_logged_in=True) == "control"

        # If not logged in, should distribute into variants
        variants_seen = set()
        for i in range(100):
            variant = get_variant("Test_Logged_Out", f"user_{i}", is_logged_in=False)
            assert variant in ["control", "treatment"]
            variants_seen.add(variant)

        assert len(variants_seen) > 1
    finally:
        ACTIVE_EXPERIMENTS.pop("Test_Logged_Out", None)


def test_get_user_experiments_audience():
    ACTIVE_EXPERIMENTS["Test_User_Exp_Audience"] = {
        "variants": {
            "control": 20,
            "treatment": 80,
        },
        "audience": Audience.LOGGED_IN,
    }
    try:
        # If not logged in, should get control
        experiments = get_user_experiments("user_456", is_logged_in=False)
        assert experiments["Test_User_Exp_Audience"] == "control"

        # If logged in, should evaluate variant
        experiments_logged_in = get_user_experiments("user_456", is_logged_in=True)
        assert experiments_logged_in["Test_User_Exp_Audience"] in ["control", "treatment"]
    finally:
        ACTIVE_EXPERIMENTS.pop("Test_User_Exp_Audience", None)
