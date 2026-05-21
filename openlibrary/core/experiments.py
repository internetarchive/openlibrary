import hashlib

ACTIVE_EXPERIMENTS = {
    "AB_Testing": {
        "control": 25,
        "a": 35,
        "b": 35,
    }
}


def get_variant(experiment_name: str, user_identifier: str) -> str:
    """Deterministically assigns a user to a variant based on configured weights."""
    if not user_identifier or experiment_name not in ACTIVE_EXPERIMENTS:
        return "control"

    variants = ACTIVE_EXPERIMENTS[experiment_name]

    hash_key = f"{experiment_name}-{user_identifier}".encode()
    bucket = int(hashlib.md5(hash_key).hexdigest()[:8], 16) % 100

    cumulative_weight = 0
    for variant, weight in variants.items():
        cumulative_weight += weight
        if bucket < cumulative_weight:
            return variant

    return "control"


def get_user_experiments(user_identifier: str) -> dict[str, str]:
    """Evaluates all active experiments for a user."""
    return {exp: get_variant(exp, user_identifier) for exp in ACTIVE_EXPERIMENTS}
