from dataclasses import dataclass

import requests

from infogami import config
from openlibrary.core import cache
from openlibrary.core.pd import make_pd_request_query
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


def get_pd_org(identifier: str) -> dict:
    """Returns the name of the organization associated with the given identifier.
    Falls back to vtmas_disabilityresources if no match is found.
    """
    orgs = cached_pd_org_query()
    vtmas = {
        "identifier": "vtmas_disabilityresources",
        "title": "Vermont Mutual Aid Society",
    }
    for org in orgs:
        if org['identifier'] == identifier:
            return org

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

    org_list = response.json().get("response", {}).get("docs", []) or []
    return sorted(org_list, key=lambda org: org.get("title", "").lower())


def cached_pd_org_query() -> list:
    mc = cache.memcache_memoize(make_pd_org_query, "pd-org-query", timeout=DAY_SECS)
    if not (results := mc() or []):
        mc.memcache_delete_by_args()
        mc()
    return results


def get_pd_dashboard_data() -> dict:
    def enrich_data(_request_data):
        for d in _request_data:
            pda = d['pda']
            d['display_name'] = (
                "No Qualifying Authority Selected"
                if pda == "unqualified"
                else get_pd_org(pda)['title']
            )

    request_data = make_pd_request_query()
    totals = request_data and request_data.pop(0)
    enrich_data(request_data)
    return {
        "data": request_data,
        "totals": {
            'requested': totals['requested'],
            'emailed': totals['emailed'],
            'fulfilled': totals['fulfilled'],
            'total': totals['requested'] + totals['emailed'] + totals['fulfilled'],
        },
    }


def setup():
    pass
