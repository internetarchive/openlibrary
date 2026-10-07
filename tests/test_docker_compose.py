import os
import re
import shlex

import pytest
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


I18N_DIR = "/openlibrary/openlibrary/i18n"


def _mount_targets(service: dict) -> list[str]:
    targets = []
    for volume in service.get("volumes", []):
        if isinstance(volume, dict):
            targets.append(volume["target"])
        else:
            # "source:target[:mode]"; a bare "target" is an anonymous volume.
            # ${VAR:-default} in the source contains a colon, so blank it first.
            parts = re.sub(r"\$\{[^}]*\}", "VAR", volume).split(":")
            targets.append(parts[1] if len(parts) > 1 else parts[0])
    return targets


def _shadows_i18n(target: str) -> bool:
    target = target.rstrip("/")
    return target == I18N_DIR or I18N_DIR.startswith(target + "/") or target.startswith(I18N_DIR + "/")


class TestTranslationsSource:
    """
    olbase bakes .po files from openlibrary-i18n into /openlibrary/openlibrary/i18n
    (docker/Dockerfile.olbase). A compose file serves those baked translations only
    if nothing is mounted over that directory; a checkout mounted over /openlibrary
    serves the .po files committed in this repo instead.
    """

    def test_production_serves_baked_translations(self):
        with open(p("..", "compose.production.yaml")) as f:
            prod_dc: dict = yaml.safe_load(f)
        for name, service in prod_dc["services"].items():
            shadowing = [t for t in _mount_targets(service) if _shadows_i18n(t)]
            assert not shadowing, f"production {name} mounts {shadowing} over the baked translations"

    @pytest.mark.parametrize("compose_file", ["compose.override.yaml", "compose.staging.yaml", "compose.selinux.yaml"])
    def test_checkout_mounted_files_serve_committed_translations(self, compose_file):
        # The testing server (compose.staging.yaml) is one of these, so it cannot
        # preview what production will serve.
        with open(p("..", compose_file)) as f:
            dc: dict = yaml.safe_load(f)
        for name in ("web", "fast_web"):
            assert "/openlibrary" in _mount_targets(dc["services"][name]), f"{compose_file} {name}"

    def test_near_prod_serves_committed_translations(self):
        # compose.near-prod.yaml is layered on compose.override.yaml (see its header):
        # it keeps override's web/fast_web, and its own app services mount the checkout.
        # Despite the name, it is not a path that serves baked translations.
        with open(p("..", "compose.near-prod.yaml")) as f:
            dc: dict = yaml.safe_load(f)
        assert not {"web", "fast_web"} & set(dc["services"])
        for name, service in dc["services"].items():
            if "image" in service and "solr" not in service["image"]:
                assert "/openlibrary" in _mount_targets(service), f"compose.near-prod.yaml {name}"
