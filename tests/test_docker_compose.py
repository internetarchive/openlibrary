import os

import yaml


def p(*paths):
    """Util to get absolute path from relative path"""
    return os.path.join(os.path.dirname(__file__), *paths)


class TestDockerCompose:
    def test_all_root_services_must_be_in_prod(self):
        """
        Each service in compose.yaml should also be in
        compose.production.yaml with a profile. Services without profiles will
        match with any profile, meaning the service would get deployed everywhere!
        """
        with open(p("..", "compose.yaml")) as f:
            root_dc: dict = yaml.safe_load(f)
        with open(p("..", "compose.production.yaml")) as f:
            prod_dc: dict = yaml.safe_load(f)
        root_services = set(root_dc["services"])
        prod_services = set(prod_dc["services"])
        missing = root_services - prod_services
        assert missing == set(), "compose.production.yaml missing services"

    def test_all_prod_services_need_profile(self):
        """
        Without the profiles field, a service will get deployed to _every_ server. That
        is not likely what you want. If that is what you want, add all server names to
        this service to make things explicit.
        """
        with open(p("..", "compose.production.yaml")) as f:
            prod_dc: dict = yaml.safe_load(f)
        for serv, opts in prod_dc["services"].items():
            assert "profiles" in opts, f"{serv} is missing 'profiles' field"

    def test_web_services_set_deployment_name(self):
        with open(p("..", "compose.staging.yaml")) as f:
            staging_dc: dict = yaml.safe_load(f)
        with open(p("..", "compose.production.yaml")) as f:
            prod_dc: dict = yaml.safe_load(f)

        for service_name in ("web", "fast_web"):
            assert "OL_DEPLOYMENT_NAME=testing" in staging_dc["services"][service_name]["environment"]
            assert "OL_DEPLOYMENT_NAME=production" in prod_dc["services"][service_name]["environment"]

    def test_staging_fastapi_is_front_door(self):
        """
        FastAPI (:8080) must be the public entry point on staging, like local
        dev, with web.py reachable only over the internal network via the
        fallback proxy (http://web:8080) — no published host port of its own.
        """
        with open(p("..", "compose.staging.yaml")) as f:
            staging_dc: dict = yaml.safe_load(f)

        assert staging_dc["services"]["web"].get("ports", []) == []
        assert "${FAST_WEB_PORT:-8080}:8080" in staging_dc["services"]["fast_web"]["ports"]
