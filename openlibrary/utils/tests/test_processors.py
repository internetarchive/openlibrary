import web
import time

from ..processors import RateLimitProcessor

class TestRateLimitProcessor:
    """py.test testcase for testing RateLimitProcessor.
    """
    def setup_method(self, method):
        web.ctx.ip = "127.0.0.1"

    def test_check_rate(self, monkeypatch):
        monkeypatch.setattr(time, "time", lambda: 123456)
        p = RateLimitProcessor(10)

        for i in range(10):
            assert p.check_rate() == True
        assert p.check_rate() == False

    def test_get_window(self, monkeypatch):
        p = RateLimitProcessor(10, window_size=10)

        d = web.storage(time=1)
        monkeypatch.setattr(time, "time", lambda: d.time)

        # window should continue to be the same from time 1 to 9.
        w = p.get_window()
        w['foo'] = 'bar'

        d.time = 9
        assert p.get_window() == {'foo': 'bar'}

        # and the window should get cleared when time becomes 10.
        d.time = 10
        assert p.get_window() == {}
