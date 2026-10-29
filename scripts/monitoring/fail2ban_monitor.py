from scripts.monitoring.utils import bash_run


def get_jail_list() -> list[str]:
    """
    Returns the list of currently configured fail2ban jails.
    """
    result = bash_run(
        "fail2ban-client status | grep 'Jail list'",
        capture_output=True,
    )
    jails_str = result.stdout.strip().split(":", 1)[-1].strip()
    if not jails_str:
        return []
    return [jail.strip() for jail in jails_str.split(",")]


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
