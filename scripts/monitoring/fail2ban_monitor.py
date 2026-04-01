from scripts.monitoring.utils import bash_run


def get_fail2ban_counts(jail: str) -> tuple[int, int]:
    """
    Returns (currently_failed, currently_banned) counts for the given fail2ban jail.
    """
    result = bash_run(
        f"fail2ban-client status {jail} | grep 'Currently'",
        capture_output=True,
    )
    failed = 0
    banned = 0
    for line in result.stdout.splitlines():
        line = line.strip()
        if "Currently failed:" in line:
            failed = int(line.split(":")[-1].strip())
        elif "Currently banned:" in line:
            banned = int(line.split(":")[-1].strip())
    return failed, banned
