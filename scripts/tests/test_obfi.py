import io
import os
import socket
import sys
import time
import urllib.request
from pathlib import Path
from types import MappingProxyType

import pytest

os.environ['SEED_PATH'] = 'must be truthy for obfi/decode_ip scripts to run'
from ..obfi import hide, mktable, reveal, shownames


def mock_urlopen(*args, **kwargs):
    """Mock for urllib.request.urlopen to always return seed=1234."""

    class MockRead:
        def read(self):
            return b"seed=1234"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    return MockRead()


@pytest.fixture
def get_patched_hide(monkeypatch) -> hide.HashIP:
    """
    Patch hide's call to urllib so we can use the same key and not rely
    on network connectivity.

    Give mktable a temp custom prefix to use when saving the real_ip db.
    """
    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    hash_ip = hide.HashIP()
    return hash_ip


@pytest.fixture
def get_patched_mktable(monkeypatch, tmp_path) -> mktable.HashIP:
    """
    Patch mktable's call to url so we can use the same key and not rely
    on network connectivity.

    Give mktable a temp custom prefix to use when saving the real_ip db.
    """
    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    file: Path = tmp_path / "hide_ip_map_"
    hash_ip = mktable.HashIP(real_ip_prefix=file.as_posix())

    return hash_ip


class TestHide:
    def test_get_seed(self, get_patched_hide) -> None:
        hash_ip = get_patched_hide

        assert hash_ip.seed == b"1234"
        with pytest.raises(AssertionError):
            assert hash_ip.seed == b"raise error"

    def test_hide(self, get_patched_hide) -> None:
        hash_ip = get_patched_hide

        assert hash_ip.hide("207.241.224.2") == "0.128.68.105"


class TestReveal:
    fake_lighttpd_access_log = """0.245.206.5 localhost - [04/Apr/2023:12:34:56 +0000] "GET /example.html HTTP/1.1" 200 1234 "http://www.example.com/" "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:85.0) Gecko/20100101 Firefox/85.0"
0.81.159.57 - - [04/Apr/2023:12:34:56 +0000] "GET /example.html HTTP/1.1" 200 1234 "http://www.example.com/" "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:85.0) Gecko/20100101 Firefox/85.0"
0.168.131.52 example.com - [04/Apr/2023:12:34:56 +0000] "GET /example.html HTTP/1.1" 200 1234 "http://www.example.com/" "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:85.0) Gecko/20100101 Firefox/85.0"
0.128.68.105 archive.org - [04/Apr/2023:12:34:56 +0000] "GET /example.html HTTP/1.1" 200 1234 "http://www.example.com/" "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:85.0) Gecko/20100101 Firefox/85.0"
0.1.2.3 not_in_real_ips - [04/Apr/2023:12:34:56 +0000] "GET /example.html HTTP/1.1" 200 1234 "http://www.example.com/" "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:85.0) Gecko/20100101 Firefox/85.0"
"""

    expected_output_no_replace = """0.245.206.5(127.0.0.1) localhost - [04/Apr/2023:12:34:56 +0000] "GET /example.html HTTP/1.1" 200 1234 "http://www.example.com/" "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:85.0) Gecko/20100101 Firefox/85.0"
0.81.159.57(8.8.8.8) - - [04/Apr/2023:12:34:56 +0000] "GET /example.html HTTP/1.1" 200 1234 "http://www.example.com/" "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:85.0) Gecko/20100101 Firefox/85.0"
0.168.131.52(93.184.216.34) example.com - [04/Apr/2023:12:34:56 +0000] "GET /example.html HTTP/1.1" 200 1234 "http://www.example.com/" "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:85.0) Gecko/20100101 Firefox/85.0"
0.128.68.105(207.241.224.2) archive.org - [04/Apr/2023:12:34:56 +0000] "GET /example.html HTTP/1.1" 200 1234 "http://www.example.com/" "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:85.0) Gecko/20100101 Firefox/85.0"
0.1.2.3 not_in_real_ips - [04/Apr/2023:12:34:56 +0000] "GET /example.html HTTP/1.1" 200 1234 "http://www.example.com/" "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:85.0) Gecko/20100101 Firefox/85.0"
"""

    expected_output_with_replace = """127.0.0.1 localhost - [04/Apr/2023:12:34:56 +0000] "GET /example.html HTTP/1.1" 200 1234 "http://www.example.com/" "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:85.0) Gecko/20100101 Firefox/85.0"
8.8.8.8 - - [04/Apr/2023:12:34:56 +0000] "GET /example.html HTTP/1.1" 200 1234 "http://www.example.com/" "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:85.0) Gecko/20100101 Firefox/85.0"
93.184.216.34 example.com - [04/Apr/2023:12:34:56 +0000] "GET /example.html HTTP/1.1" 200 1234 "http://www.example.com/" "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:85.0) Gecko/20100101 Firefox/85.0"
207.241.224.2 archive.org - [04/Apr/2023:12:34:56 +0000] "GET /example.html HTTP/1.1" 200 1234 "http://www.example.com/" "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:85.0) Gecko/20100101 Firefox/85.0"
0.1.2.3 not_in_real_ips - [04/Apr/2023:12:34:56 +0000] "GET /example.html HTTP/1.1" 200 1234 "http://www.example.com/" "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:85.0) Gecko/20100101 Firefox/85.0"
"""
    real_ips: MappingProxyType[str, bytes] = MappingProxyType(
        {
            "0.81.159.57": b"8.8.8.8",
            "0.168.131.52": b"93.184.216.34",
            "0.128.68.105": b"207.241.224.2",
            "0.245.206.5": b"127.0.0.1",
        }
    )

    def test_reveal_no_replace(self, monkeypatch, capsys) -> None:
        monkeypatch.setattr(sys, "stdin", io.StringIO(self.fake_lighttpd_access_log))

        revealer = reveal.IPRevealer(self.real_ips, replace=False)
        revealer.run()
        captured = capsys.readouterr()

        assert captured.out == self.expected_output_no_replace

    def test_reveal_with_replace(self, monkeypatch, capsys) -> None:
        monkeypatch.setattr(sys, "stdin", io.StringIO(self.fake_lighttpd_access_log))

        revealer = reveal.IPRevealer(self.real_ips, replace=True)
        revealer.run()
        captured = capsys.readouterr()

        assert captured.out == self.expected_output_with_replace


class TestMkTable:
    """
    Tests for mktable. All tests use a mocked urllib and temporary file for
    hide_ip_map_<yday>.
    """

    def test_get_seed(self, get_patched_mktable) -> None:
        """urllib.requests.urlopen has been patched to return a seed of 1234."""
        hash_ip = get_patched_mktable
        assert hash_ip.seed == b"1234"

    def test_seed_changes_when_yday_changes(
        self, monkeypatch, get_patched_mktable
    ) -> None:
        """Ensure the seed changes each day."""
        hash_ip = get_patched_mktable

        # Ensure the seed stays the same when hide() is executed and the day
        # has not changed.
        original_seed = hash_ip.seed
        hash_ip.hide("8.8.8.8")
        assert original_seed == hash_ip.seed

        # Patch gmtime() so that index 7 returns day yday 70000, which should
        # cause get_seed() to run again when hide() is executed. Overwrite
        # the previous seed to ensure a new seed is set when
        # hide() -> get_seed() are executed.
        monkeypatch.setattr(time, "gmtime", lambda: [0, 1, 2, 3, 4, 5, 6, 70_000])
        hash_ip.seed = 70_000
        hash_ip.hide("127.0.0.1")
        assert hash_ip.seed != 70_000

    def test_hidden_hosts_are_written_to_hide_ip_map(
        self, get_patched_mktable, monkeypatch, capsys
    ) -> None:
        """
        Add unique and duplicate IPs. Only the unique IPs should be echoed
        back to STDOUT; duplicated IPs are already in the DB.
        """
        hash_ip = get_patched_mktable
        # 127.0.0.1 is duplicated
        real_ips = "127.0.0.1\n207.241.224.2\n127.0.0.1\n8.8.8.8\n"
        expected = (
            "127.0.0.1 0.245.206.5\n207.241.224.2 0.128.68.105\n8.8.8.8 0.81.159.57\n"
        )
        monkeypatch.setattr(sys, "stdin", io.StringIO(real_ips))

        hash_ip.process_input()
        captured = capsys.readouterr()
        assert captured.out == expected


class TestShownames:
    """
    Tests for shownames. socket.getbyhostaddr is mocked, so this only tests
    that if an ostensibly valid IP address is found in STDIN, that its
    resolved hostname is appended and the line is printed to STDOUT.
    """

    def get_hostname(self, ip):
        """Give some static hostname responses."""
        if ip == "207.241.224.2":
            return ("www.archive.org", [], ["207.241.224.2"])
        elif ip == "8.8.8.8":
            return ("dns.google", [], ["8.8.8.8"])
        else:
            raise ValueError("Unknown host")

    def test_shownames(self, monkeypatch, capsys) -> None:
        """
        When an IP resolves, stick it in [brackets] next to the IP.
        This tests both an IP that resolves and one that doesn't.
        """
        revealed_lighttpd_log = """0.128.68.105(207.241.224.2) archive.org - [04/Apr/2023:12:34:56 +0000] "GET /example.html HTTP/1.1" 200 1234 "http://www.example.com/" "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:85.0) Gecko/20100101 Firefox/85.0"
0.168.131.52(93.184.216.34) example.com - [04/Apr/2023:12:34:56 +0000] "GET /example.html HTTP/1.1" 200 1234 "http://www.example.com/" "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:85.0) Gecko/20100101 Firefox/85.0"\n"""
        expected = """0.128.68.105(www.archive.org[207.241.224.2]) archive.org - [04/Apr/2023:12:34:56 +0000] "GET /example.html HTTP/1.1" 200 1234 "http://www.example.com/" "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:85.0) Gecko/20100101 Firefox/85.0"
0.168.131.52(93.184.216.34) example.com - [04/Apr/2023:12:34:56 +0000] "GET /example.html HTTP/1.1" 200 1234 "http://www.example.com/" "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:85.0) Gecko/20100101 Firefox/85.0"\n"""

        monkeypatch.setattr(socket, "gethostbyaddr", self.get_hostname)
        monkeypatch.setattr(sys, "stdin", io.StringIO(revealed_lighttpd_log))
        shownames.run()
        captured = capsys.readouterr()
        assert captured.out == expected
