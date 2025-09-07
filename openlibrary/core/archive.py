"""Simple Save Page Now client."""

import os
import requests

try:
    from infogami import config
except ImportError:
    config = None


def is_already_archived(url):
    """Check if URL is already archived in Wayback Machine.
    
    Returns:
        True if archived, False if not archived or error
    """
    try:
        # Check Wayback Machine availability API
        check_url = f"http://archive.org/wayback/available?url={url}"
        response = requests.get(check_url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return bool(data.get('archived_snapshots', {}).get('closest'))
    except Exception:
        pass
    return False


def archive_url(url, access_key=None, secret_key=None, if_not_archived_within="1d", check_existing=True):
    """Archive a URL using Save Page Now API.
    
    Args:
        url: URL to archive
        access_key: IA access key (optional, uses config/env)
        secret_key: IA secret key (optional, uses config/env)  
        if_not_archived_within: Only archive if not archived within timeframe
                               (e.g., "1d", "3h", "120" for 120 seconds)
        check_existing: Check if URL is already archived before attempting
    
    Returns:
        Job ID if successful, "ALREADY_ARCHIVED" if exists, error string if failed
    """

    # TODO review this guardrail to see if we should keep it
    if check_existing and is_already_archived(url):
        return "ALREADY_ARCHIVED"
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
        "Accept": "application/json"
    }
    
    data = {
        "url": url,
        "if_not_archived_within": if_not_archived_within
    }
    
    try:
        response = requests.post(
            "https://web.archive.org/save",
            headers=headers,
            data=data,
            timeout=30
        )
        if response.status_code == 200:
            result = response.json()
            return result.get('job_id', f"ERROR_NO_JOB_ID_{response.status_code}")
        else:
            return f"ERROR_HTTP_{response.status_code}"
    except Exception as e:
        return f"ERROR_EXCEPTION_{str(e)[:50]}"