import os
import yaml


def p(*paths):
    """Util to get absolute path from relative path"""
    return os.path.join(os.path.dirname(__file__), *paths)


class TestDockerCompose:
    def test_all_root_services_must_be_in_prod(self):
        """
        Each service in docker-compose.yml should also be in
        docker-compose.production.yml with a profile. Services without profiles will
        match with any profile, meaning the service would get deployed everywhere!
        """
        with open(p('..', 'docker-compose.yml')) as f:
            root_dc = yaml.safe_load(f)  # type: dict
        with open(p('..', 'docker-compose.production.yml')) as f:
            prod_dc = yaml.safe_load(f)  # type: dict
        root_services = set(root_dc['services'].keys())
        prod_services = set(prod_dc['services'].keys())
        missing = root_services - prod_services
        assert missing == set(), "docker-compose.production.yml missing services"

    def test_all_prod_services_need_profile(self):
        """
        Without the profiles field, a service will get deployed to _every_ server. That
        is not likely what you want. If that is what you want, add all server names to
        this service to make things explicit.
        """
        with open(p('..', 'docker-compose.production.yml')) as f:
            prod_dc = yaml.safe_load(f)  # type: dict
        for serv, opts in prod_dc['services'].items():
            assert 'profiles' in opts, f"{serv} is missing 'profiles' field"
