import pytest
from unittest.mock import MagicMock, patch

from scripts.monitoring.fail2ban_monitor import get_fail2ban_counts

# grep -m1 'Number of entries:' returns just the matched line
FAKE_IPSET_OUTPUT = "Number of entries: 468"


def test_get_fail2ban_counts():
    mock_result = MagicMock()
    mock_result.stdout = FAKE_IPSET_OUTPUT

    with patch("scripts.monitoring.fail2ban_monitor.bash_run", return_value=mock_result):
        failed, banned = get_fail2ban_counts("HTTP429")

    assert failed == 0
    assert banned == 468


def test_get_fail2ban_counts_raises_on_missing_output():
    mock_result = MagicMock()
    mock_result.stdout = ""

    with patch("scripts.monitoring.fail2ban_monitor.bash_run", return_value=mock_result):
        with pytest.raises(RuntimeError, match="Unable to parse fail2ban banned IP count"):
            get_fail2ban_counts("HTTP429")
