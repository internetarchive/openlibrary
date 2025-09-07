#!/usr/bin/env python3

## Note: This is not final integration code, it's just a test to see if the archive.org API is working to test out the changes.
## Sample test file to quickly test archive.py
"""Test Save Page Now with real URLs."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from openlibrary.core.archive import archive_url

# Test URLs source : https://colab.research.google.com/drive/1y7c4n34N6oahlMjImDfG1QzembHWUJW4#scrollTo=g4YZshpc_ICP
urls = [
    "https://www.atsdr.cdc.gov/place-health/php/svi/index.html",
    "https://nida.nih.gov/nidamed-medical-health-professionals/health-professions-education/words-matter-terms-to-use-avoid-when-talking-about-addiction",
    "https://www.cdc.gov/health-equity/index.html",
    "https://www.cdc.gov/health-equity-chronic-disease/index.html",
    "https://www.cdc.gov/pcd/issues/2020/20_0350.htm",
    "https://www.cdc.gov/pcd/issues/2020/20_0317.htm",
    "https://www.cdc.gov/pcd/collections/Public_Health_and_Pharmacy.htm",
    "https://hdsbpc.cdc.gov/s/article/Implementation-Considerations-for-Collaborative-Drug-Therapy-Management",
    "https://www.cdc.gov/nchs/nsfg/nsfg-questionnaires.htm",
    "https://www.ncei.noaa.gov/access"
    "https://community.purpleair.com/t/purpleair-data-download-tool/3787",
    "https://www.cdc.gov/health-equity/",
    "https://minorityhealth.hhs.gov/minority-population-profiles",
    "https://aspe.hhs.gov/topics/health-health-care",
    "https://odphp.health.gov/healthypeople",
]


def main():
    if len(sys.argv) > 1:
        # Archive single URL
        url = sys.argv[1]
        print(f"Archiving: {url}")
        result = archive_url(url)

        if result.startswith('spn2-'):
            print("SUCCESS - URL archived!")
            print(f"Job ID: {result}")
            print(f"Check status: https://web.archive.org/save/status/{result}")
            print(f"View archive: https://web.archive.org/web/*/{url}")
        elif result == "ALREADY_ARCHIVED":
            print("SKIPPED - URL already archived!")
            print(f"View archive: https://web.archive.org/web/*/{url}")
        elif result == "NO_CREDENTIALS":
            print("No credentials found!")
            print("Set IA_ACCESS_KEY and IA_SECRET_KEY environment variables")
        else:
            print(f"FAILED: {result}")
    else:
        # Archive test URLs
        print(f"Archiving {len(urls)} URLs...")
        result = archive_url(urls[0])  # Test first URL to check credentials

        if result == "NO_CREDENTIALS":
            print("No credentials found!")
            print("Set IA_ACCESS_KEY and IA_SECRET_KEY environment variables")
            print("Get them from: https://archive.org/account/s3.php")
            return

        # Test all URLs
        success_count = 0
        skipped_count = 0
        for i, url in enumerate(urls, 1):
            result = archive_url(url)
            if result.startswith('spn2-'):
                success_count += 1
                status = "ARCHIVED"
                wayback_url = f"https://web.archive.org/save/status/{result}"
            elif result == "ALREADY_ARCHIVED":
                skipped_count += 1
                status = "SKIPPED (already archived)"
                wayback_url = f"https://web.archive.org/web/*/{url}"
            else:
                status = f"FAILED ({result})"
                wayback_url = ""

            print(f"{i:2d}. {status}")
            print(f"    URL: {url}")
            if result.startswith('spn2-'):
                print(f"    Job: {result}")
            if wayback_url:
                print(f"    View: {wayback_url}")
            print()

        print(
            f"Summary: {success_count} archived, {skipped_count} skipped, {len(urls) - success_count - skipped_count} failed"
        )


if __name__ == "__main__":
    main()
