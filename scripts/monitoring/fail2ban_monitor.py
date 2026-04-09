from scripts.monitoring.utils import bash_run


def get_fail2ban_counts(ipset_name: str) -> tuple[int, int]:
    """
    Returns (currently_failed, currently_banned) counts for the given fail2ban ipset.

    Uses `sudo ipset list f2b-{ipset_name}` as the authoritative source for banned IPs
    after the upgrade to fail2ban 1.1.0-8 with the `iptables-ipset-proto6` banaction.

    Note: the failed count is not available via ipset and is always returned as 0.
    """
    result = bash_run(
        f"sudo ipset list f2b-{ipset_name}",
        capture_output=True,
    )
    banned = 0
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("Number of entries:"):
            banned = int(line.split(":")[-1].strip())
            break
    return 0, banned
