from unittest.mock import MagicMock, patch

from scripts.monitoring.fail2ban_monitor import get_fail2ban_counts

FAKE_FAIL2BAN_OUTPUT = """
Status for the jail: nginx-429
|- Filter
|  |- Currently failed: 193
|  |- Total failed:     56440304
|  `- File list:        /1/var/log/nginx/error.log
`- Actions
   |- Currently banned: 141
   |- Total banned:     661976
   `- Banned IP list:   08.07.04.02 04.06.02.09
"""


def test_get_fail2ban_counts():
    mock_result = MagicMock()
    mock_result.stdout = FAKE_FAIL2BAN_OUTPUT

    with patch(
        "scripts.monitoring.fail2ban_monitor.bash_run", return_value=mock_result
    ):
        failed, banned = get_fail2ban_counts("nginx-429")

    assert failed == 193
    assert banned == 141
