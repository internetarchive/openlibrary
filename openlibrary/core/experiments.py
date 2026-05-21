import hashlib
from typing import Any

ACTIVE_EXPERIMENTS: dict[str, dict[str, Any]] = {
    "AB_Testing": {
        "variants": {
            "control": 30,
            "a": 35,
            "b": 35,
        },
        "authorized_only": False,
    }
}


def get_variant(experiment_name: str, user_identifier: str | None, is_logged_in: bool = False) -> str:
    """Deterministically assigns a user to a variant based on configured weights."""
    if not user_identifier or experiment_name not in ACTIVE_EXPERIMENTS:
        return "control"

    exp_config = ACTIVE_EXPERIMENTS[experiment_name]
    if exp_config.get("authorized_only") and not is_logged_in:
        return "control"

    variants = exp_config.get("variants", {})

    hash_key = f"{experiment_name}-{user_identifier}".encode()
    bucket = int(hashlib.md5(hash_key).hexdigest()[:8], 16) % 100

    cumulative_weight = 0
    for variant, weight in variants.items():
        cumulative_weight += weight
        if bucket < cumulative_weight:
            return variant

    return "control"


def get_user_experiments(
    user_identifier: str | None,
    overrides: dict[str, str] | None = None,
    is_logged_in: bool = False,
) -> dict[str, str]:
    """Evaluates all active experiments for a user, applying optional overrides."""
    experiments = {}
    for exp, exp_config in ACTIVE_EXPERIMENTS.items():
        variants = exp_config.get("variants", {})
        override_key = f"experiment_{exp}"
        if overrides and override_key in overrides and overrides[override_key] in variants:
            experiments[exp] = overrides[override_key]
        else:
            experiments[exp] = get_variant(exp, user_identifier, is_logged_in=is_logged_in)
    return experiments
