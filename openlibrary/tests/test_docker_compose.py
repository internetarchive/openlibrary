from pathlib import Path

import yaml

root_dir_path = Path(__file__).parent.parent.parent


def test_all_root_services_must_be_in_prod():
    """
    Each service in compose.yaml should also be in
    compose.production.yaml with a profile. Services without profiles will
    match with any profile, meaning the service would get deployed everywhere!
    """
    with open(root_dir_path / 'compose.yaml') as f:
        root_dc: dict = yaml.safe_load(f)
    with open(root_dir_path / 'compose.production.yaml') as f:
        prod_dc: dict = yaml.safe_load(f)
    root_services = set(root_dc['services'])
    prod_services = set(prod_dc['services'])
    missing = root_services - prod_services
    assert missing == set(), "compose.production.yaml missing services"


def test_all_prod_services_need_profile():
    """
    Without the profiles field, a service will get deployed to _every_ server. That
    is not likely what you want. If that is what you want, add all server names to
    this service to make things explicit.
    """
    with open(root_dir_path / 'compose.production.yaml') as f:
        prod_dc: dict = yaml.safe_load(f)
    for serv, opts in prod_dc['services'].items():
        assert 'profiles' in opts, f"{serv} is missing 'profiles' field"


def test_shared_constants():
    # read the value in compose.yaml
    with open(root_dir_path / 'compose.yaml') as f:
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
    from openlibrary.core.bookshelves import FILTER_BOOK_LIMIT

    assert solr_opts_max_boolean_clauses >= FILTER_BOOK_LIMIT


def test_docker_web_nodes():
    """
    Test the Docker web nodes in compose.production.yaml to ensure that they have
    different hostnames and profiles but that all other keys and values are the same.
    """
    with open(root_dir_path / "compose.production.yaml") as f:
        production_services = yaml.safe_load(f).get("services")
    assert production_services
    web = production_services.get("web")
    web2 = production_services.get("web2")
    assert web
    assert web2
    for key in ("hostname", "profiles"):
        assert web.pop(key) != web2.pop(key)  # Remove keys that should be different.
    assert web == web2  # All remaining keys and values should be the same.
