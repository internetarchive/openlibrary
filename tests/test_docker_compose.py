import os
import re
import shlex

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

    def test_node_exporter_matches_across_environments(self):
        """
        node-exporter should be configured identically in staging and production
        (aside from production's per-server 'profiles' field) so that the metrics
        we collect are consistent across environments.
        """
        with open(p("..", "compose.staging.yaml")) as f:
            staging_dc: dict = yaml.safe_load(f)
        with open(p("..", "compose.production.yaml")) as f:
            prod_dc: dict = yaml.safe_load(f)

        staging_node_exporter = dict(staging_dc["services"]["node-exporter"])
        prod_node_exporter = dict(prod_dc["services"]["node-exporter"])
        del prod_node_exporter["profiles"]

        assert staging_node_exporter == prod_node_exporter, "node-exporter config differs between staging and production"

    def test_provision_node_exporter_matches_production(self):
        """
        provision_olserver.sh starts node-exporter with a plain `docker run` on
        servers that aren't deployed with compose; it should match the
        compose.production.yaml service so metrics are consistent across servers.
        """
        with open(p("..", "scripts", "deployment", "provision_olserver.sh")) as f:
            script = f.read()
        test_name = "test_provision_node_exporter_matches_production"
        match = re.search(
            rf"^\s*## TEST-START: {test_name}\n(.*?)^\s*## TEST-END: {test_name}$",
            script,
            re.MULTILINE | re.DOTALL,
        )
        assert match, f"TEST-START/TEST-END markers for {test_name} not found"
        args = shlex.split(match.group(1).replace("\\\n", " "))
        assert args[:4] == ["sudo", "docker", "run", "-d"]
        args = args[4:]

        run_config: dict = {"volumes": [], "logging": {"options": {}}}
        flag_to_key = {
            "--restart": "restart",
            "--hostname": "hostname",
            "--network": "network_mode",
            "--pid": "pid",
        }
        while args[0].startswith("-"):
            flag, value = args.pop(0), args.pop(0)
            if flag == "--name":
                assert value == "node-exporter"
            elif flag == "-v":
                run_config["volumes"].append(value)
            elif flag == "--log-opt":
                key, _, opt = value.partition("=")
                run_config["logging"]["options"][key] = opt
            else:
                assert flag in flag_to_key, f"Unhandled docker run flag {flag}"
                run_config[flag_to_key[flag]] = value
        run_config["image"] = args.pop(0)
        run_config["command"] = args

        with open(p("..", "compose.production.yaml")) as f:
            prod_dc: dict = yaml.safe_load(f)
        prod_node_exporter = dict(prod_dc["services"]["node-exporter"])
        del prod_node_exporter["profiles"]
        # `$$` is compose's escape for a literal `$`
        prod_node_exporter["command"] = [arg.replace("$$", "$") for arg in prod_node_exporter["command"]]

        assert run_config == prod_node_exporter, "provision_olserver.sh node-exporter differs from compose.production.yaml"
