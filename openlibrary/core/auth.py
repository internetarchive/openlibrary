import hashlib
import hmac
import socket
import string
import time
from urllib.parse import urlparse

import requests

from infogami import config
from openlibrary.core import cache


class TimedOneTimePassword:

    VALID_MINUTES = 10

    @staticmethod
    def shorten(digest: str, length=6) -> str:
        """
        Convert an HMAC digest (bytes) into a short alphanumeric code.
        """
        alphabet = string.digits + string.ascii_uppercase
        num = int.from_bytes(digest, "big")
        base36 = ""
        while num > 0:
            num, i = divmod(num, 36)
            base36 = alphabet[i] + base36
        return base36[:length].lower()

    @classmethod
    def generate(
        cls, service_ip: str, client_email: str, client_ip: str, ts: int | None = None
    ) -> str:
        seed = config.get("otp_seed")
        ts = ts or int(time.time() // 60)
        payload = f"{service_ip}:{client_email}:{client_ip}:{ts}".encode()
        digest = hmac.new(seed.encode('utf-8'), payload, hashlib.sha256).digest()
        return cls.shorten(digest)

    @staticmethod
    def verify_service(service_ip: str, service_url: str) -> bool:
        """Doesn't work because of VPN"""
        parsed = urlparse(service_url)
        resolved_ip = socket.gethostbyname(parsed.hostname)
        r = requests.get(service_url, timeout=5)
        return (
            service_url.startswith("https://")
            and resolved_ip == service_ip
            and bool(r.json())
        )

    @classmethod
    def is_ratelimited(cls, ttl=60, service_ip="", **kwargs):
        def ratelimit_error(key, ttl):
            return {"error": "ratelimit", "ratelimit": {"ttl": ttl, "key": key}}

        mc = cache.get_memcache()
        # Limit requests to 1 / ttl per client
        for key, value in kwargs.items():
            cache_key = f"otp-client:{service_ip}:{key}:{value}"
            if not mc.add(cache_key, 1, expires=ttl):
                return ratelimit_error(cache_key, ttl)

        # Limit globally to 3 attempts per email and ip per / ttl
        for key, value in kwargs.items():
            cache_key = f"otp-global:{key}:{value}"
            count = (mc.get(cache_key) or 0) + 1
            mc.set(cache_key, count, expires=ttl)
            if count > 3:
                return ratelimit_error(cache_key, ttl)

    @classmethod
    def validate(cls, otp, service_ip, client_email, client_ip, ts):
        expected_otp = cls.generate(service_ip, client_email, client_ip, ts)
        return hmac.compare_digest(otp.lower(), expected_otp.lower())

    @classmethod
    def is_valid(cls, client_email, client_ip, service_ip, otp):
        now_minute = int(time.time() // 60)
        for delta in range(cls.VALID_MINUTES):
            minute_ts = now_minute - delta
            if cls.validate(otp, service_ip, client_email, client_ip, minute_ts):
                return True
        return False
