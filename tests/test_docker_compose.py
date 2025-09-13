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
        with open(p('..', 'compose.yaml')) as f:
            root_dc: dict = yaml.safe_load(f)
        with open(p('..', 'compose.production.yaml')) as f:
            prod_dc: dict = yaml.safe_load(f)
        root_services = set(root_dc['services'])
        prod_services = set(prod_dc['services'])
        missing = root_services - prod_services
        assert missing == set(), "compose.production.yaml missing services"

    def test_all_prod_services_need_profile(self):
        """
        Without the profiles field, a service will get deployed to _every_ server. That
        is not likely what you want. If that is what you want, add all server names to
        this service to make things explicit.
        """
        with open(p('..', 'compose.production.yaml')) as f:
            prod_dc: dict = yaml.safe_load(f)
        for serv, opts in prod_dc['services'].items():
            assert 'profiles' in opts, f"{serv} is missing 'profiles' field"

    def test_shared_constants(self):
        # read the value in compose.yaml
        with open(p('..', 'compose.yaml')) as f:
            prod_dc: dict = yaml.safe_load(f)
        solr_service = prod_dc['services']['solr']
        solr_opts = next(
            var.split('=', 1)[1]
            for var in solr_service['environment']
            if var.startswith('SOLR_OPTS=')
        )
        solr_opts_max_boolean_clauses = next(
            int(opt.split('=', 1)[1])
            for opt in solr_opts.split()
            if opt.startswith('-Dsolr.max.booleanClauses')
        )

        # read the value in openlibrary/core/bookshelves.py
        from openlibrary.core.bookshelves import FILTER_BOOK_LIMIT  # noqa: PLC0415

        assert solr_opts_max_boolean_clauses >= FILTER_BOOK_LIMIT
