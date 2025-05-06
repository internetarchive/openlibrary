from dataclasses import dataclass

import requests

from infogami import config
from openlibrary.core import cache
from openlibrary.i18n import gettext as _
from openlibrary.utils.dateutil import DAY_SECS


@dataclass
class PDOption:
    """Represents an option in a print-disability qualifying organization select element"""

    label: str
    value: str


def get_pd_options() -> list[PDOption]:
    """Returns a list of all print-disability qualifying organization options"""
    options = [
        PDOption("BARD", "ia_nlsbardaccess_disabilityresources"),
        PDOption("BookShare", "ia_bookshareaccess_disabilityresources"),
        PDOption("ACE", "aceportalocul_disabilityresources"),
        PDOption(_("I don't have one yet"), "unqualified"),
    ]

    pd_orgs = cached_pd_org_query()
    options += [PDOption(org.get("title"), org.get("identifier")) for org in pd_orgs]

    return options


def get_pd_org(identifier: str) -> str | None:
    """Returns the name of the organization associated with the given identifier.
    Falls back to vtmas_disabilityresources if no match is found.
    """
    orgs = cached_pd_org_query()
    vtmas = None
    for org in orgs:
        if org['identifier'] == identifier:
            return org
        if org['identifier'] == 'vtmas_disabilityresources':
            vtmas = org
    return vtmas


def make_pd_org_query() -> list:
    """Returns a list of items found in the "Qualifying Authorities for Print-Disabled Access" collection"""
    base_url = config.get("bookreader_host", "")
    if not base_url:
        return []
    params = "q=collection:print_disability_access&fl[]=identifier,title&rows=1000&page=1&output=json"
    url = f"https://{base_url}/advancedsearch.php?{params}"
    try:
        response = requests.get(url)
        response.raise_for_status()
    except requests.HTTPError:
        return []
    except requests.exceptions.JSONDecodeError:
        return []

    return response.json().get("response", {}).get("docs", []) or []


@cache.memoize(engine="memcache", key="pd-org-query", expires=DAY_SECS)
def cached_pd_org_query() -> list:
    return make_pd_org_query()


def setup():
    pass
