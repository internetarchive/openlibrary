import hashlib
from typing import Final, Literal, TypedDict


class Audience:
    """Constants for experiment audience targeting."""

    ALL: Final = "all"
    LOGGED_IN: Final = "logged_in"
    LOGGED_OUT: Final = "logged_out"


class ExperimentConfig(TypedDict, total=False):
    """Type schema for autocomplete and static analysis."""

    variants: dict[str, int]
    audience: Literal["all", "logged_in", "logged_out"]


ACTIVE_EXPERIMENTS: dict[str, ExperimentConfig] = {
    "Sample_Experiment_1": {
        "variants": {"control": 30, "a": 35, "b": 35},
        "audience": Audience.ALL,
    },
    "Sample_Experiment_2": {
        "variants": {"control": 50, "treatment": 50},
        "audience": Audience.LOGGED_OUT,
    },
    "Sample_Experiment_3": {
        "variants": {"control": 50, "treatment": 50},
        "audience": Audience.LOGGED_IN,
    },
}


def get_variant(experiment_name: str, user_identifier: str | None, is_logged_in: bool = False) -> str:
    """Assigns a user to a variant based on configured weights and audience rules."""
    if not user_identifier or experiment_name not in ACTIVE_EXPERIMENTS:
        return "control"

    config = ACTIVE_EXPERIMENTS[experiment_name]
    audience = config.get("audience", Audience.ALL)

    if audience == Audience.LOGGED_IN and not is_logged_in:
        return "control"
    if audience == Audience.LOGGED_OUT and is_logged_in:
        return "control"

    hash_key = f"{experiment_name}-{user_identifier}".encode()
    bucket = int(hashlib.md5(hash_key).hexdigest()[:8], 16) % 100

    cumulative_weight = 0
    for variant, weight in config.get("variants", {}).items():
        cumulative_weight += weight
        if bucket < cumulative_weight:
            return variant

    return "control"


def get_user_experiments(
    user_identifier: str | None,
    overrides: dict[str, str] | None = None,
    is_logged_in: bool = False,
) -> dict[str, str]:
    """Evaluates all active experiments for a user, handling optional overrides."""
    overrides = overrides or {}
    results = {}

    for exp_name, config in ACTIVE_EXPERIMENTS.items():
        override_val = overrides.get(f"experiment_{exp_name}")

        if override_val in config.get("variants", {}):
            results[exp_name] = override_val
        else:
            results[exp_name] = get_variant(exp_name, user_identifier, is_logged_in)

    return results
