import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from openlibrary.core.ia import get_ia_s3_keys, save_page_now

# Live URLs (integration). Will be called only when creds are present.
URLS = [
    "https://www.atsdr.cdc.gov/place-health/php/svi/index.html",
    "https://nida.nih.gov/nidamed-medical-health-professionals/health-professions-education/words-matter-terms-to-use-avoid-when-talking-about-addiction",
    "https://www.cdc.gov/health-equity/index.html",
    "https://www.cdc.gov/health-equity-chronic-disease/index.html",
    "https://www.cdc.gov/pcd/issues/2020/20_0350.htm",
    "https://www.cdc.gov/pcd/issues/2020/20_0317.htm",
    "https://www.cdc.gov/pcd/collections/Public_Health_and_Pharmacy.htm",
    "https://hdsbpc.cdc.gov/s/article/Implementation-Considerations-for-Collaborative-Drug-Therapy-Management",
    "https://www.cdc.gov/nchs/nsfg/nsfg-questionnaires.htm",
]


_access, _secret = get_ia_s3_keys()
requires_creds = pytest.mark.skipif(
    not (_access and _secret),
    reason="IA credentials not available via internetarchive session/config; skipping live SPN tests",
)


@requires_creds
@pytest.mark.parametrize("url", URLS)
def test_save_page_now_integration(url):
    result = save_page_now(url)
    assert isinstance(result, str)
    assert result == "ALREADY_ARCHIVED" or result.startswith("spn2-"), result
