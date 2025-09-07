"""Simple Save Page Now client."""

import os

import requests

try:
    from infogami import config
except ImportError:
    config = None


def archive_url(url, access_key=None, secret_key=None):
    """Archive a URL using Save Page Now API.

    Args:
        url: URL to archive
        access_key: IA access key (optional, uses config/env)
        secret_key: IA secret key (optional, uses config/env)

    Returns:
        Job ID on success, error string on failure
    """
    # Try config first (for deployment), then env vars (for testing)
    if not access_key or not secret_key:
        if config:
            # Use the same S3 credentials as other IA services
            s3_config = config.get('ia_ol_xauth_s3')
            if s3_config:
                access_key = access_key or s3_config.get('s3_key')
                secret_key = secret_key or s3_config.get('s3_secret')

        # Fallback to environment variables for testing
        access_key = access_key or os.environ.get('IA_ACCESS_KEY')
        secret_key = secret_key or os.environ.get('IA_SECRET_KEY')

    if not access_key or not secret_key:
        return "NO_CREDENTIALS"

    headers = {
        "Authorization": f"LOW {access_key}:{secret_key}",
        "Accept": "application/json",
    }

    data = {"url": url}

    try:
        response = requests.post(
            "https://web.archive.org/save", headers=headers, data=data, timeout=30
        )
        if response.status_code == 200:
            result = response.json()
            return result.get('job_id', f"ERROR_NO_JOB_ID_{response.status_code}")
        else:
            return f"ERROR_HTTP_{response.status_code}"
    except Exception as e:
        return f"ERROR_EXCEPTION_{str(e)[:50]}"
