from unittest.mock import MagicMock, patch

from scripts.monitoring.fail2ban_monitor import get_fail2ban_counts

FAKE_IPSET_OUTPUT = """
Name: f2b-HTTP429
Type: hash:ip
Revision: 4
Header: family inet hashsize 1024 maxelem 65536 timeout 0
Size in memory: 49544
References: 1
Number of entries: 468
Members:
1.1.1.1 timeout 0
2.2.2.2 timeout 0
"""


def test_get_fail2ban_counts():
    mock_result = MagicMock()
    mock_result.stdout = FAKE_IPSET_OUTPUT

    with patch("scripts.monitoring.fail2ban_monitor.bash_run", return_value=mock_result):
        failed, banned = get_fail2ban_counts("HTTP429")

    assert failed == 0
    assert banned == 468
