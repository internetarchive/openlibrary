import os

import yaml


def p(*paths):
    """Util to get absolute path from relative path"""
    return os.path.join(os.path.dirname(__file__), *paths)


class _PortPrefixLoader(yaml.SafeLoader):
    """compose.port-prefix.yaml uses the compose-spec `!override` merge tag,
    which plain yaml.safe_load doesn't know how to construct."""


def _construct_override(loader: yaml.SafeLoader, node: yaml.Node) -> list:
    assert isinstance(node, yaml.SequenceNode)
    return loader.construct_sequence(node)


_PortPrefixLoader.add_constructor("!override", _construct_override)


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

    def test_all_ported_services_are_in_port_prefix(self):
        """
        Each service in compose.yaml/compose.override.yaml that publishes a port
        should also appear in compose.port-prefix.yaml, so it gets a collision-free
        port when running multiple instances side by side.
        """
        with open(p("..", "compose.yaml")) as f:
            root_dc: dict = yaml.safe_load(f)
        with open(p("..", "compose.override.yaml")) as f:
            override_dc: dict = yaml.safe_load(f)
        with open(p("..", "compose.port-prefix.yaml")) as f:
            port_prefix_dc: dict = yaml.load(f, Loader=_PortPrefixLoader)

        ported_services = {serv for dc in (root_dc, override_dc) for serv, opts in dc["services"].items() if opts.get("ports")}
        port_prefix_services = set(port_prefix_dc["services"])
        missing = ported_services - port_prefix_services
        assert missing == set(), "compose.port-prefix.yaml missing services with ports"
