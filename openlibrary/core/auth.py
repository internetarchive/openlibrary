import datetime
import hashlib
import hmac
import socket
import string
import time
from urllib.parse import urlparse

import requests
from infogami import config

from openlibrary.core import cache


class ExpiredTokenError(Exception):
    pass


class MissingKeyError(Exception):
    pass


class HMACToken:
    @staticmethod
    def verify(
        digest: str,
        msg: str,
        secret_key_name: str,
        delimiter: str = "|",
        unix_time=False,
    ) -> bool:
        """
        Verify an HMAC digest against a message with timestamp validation.

        This method validates that the provided HMAC digest matches the expected
        digest for the given message, and that the token has not expired. The
        message is expected to contain an ISO format timestamp as its last
        delimiter-separated component.

        To mitigate timing attacks, all cryptographic operations are performed
        before raising any exceptions, ensuring constant-time execution regardless
        of which validation fails first.

        Args:
            digest: The HMAC digest to verify (hexadecimal string).
            msg: The message to verify, which must end with a delimiter-separated
                ISO format timestamp (e.g., "data|2024-12-31T23:59:59+00:00").
            secret_key_name: The configuration key name used to retrieve the
                secret key for HMAC computation.
            delimiter: The character used to separate message components.
                Defaults to "|".
            unix_time: If True, the timestamp section of the message must be
                formatted as a Unix timestamp (in seconds).  Timestamps may
                include fractions of a second.
                Example value: `data|1772503772.012154`

        Returns:
            bool: True if the digest is valid and the token has not expired.

        Raises:
            ExpiredTokenError: If the timestamp in the message indicates the
                token has expired (raised after digest comparison).
            ValueError: If the secret key cannot be found in the configuration
                (raised after digest comparison).
        """

        err: Exception | None = None

        current_time: float | datetime.datetime = time.time() if unix_time else datetime.datetime.now(datetime.UTC)
        expiry_str = msg.rsplit(delimiter, maxsplit=1)[-1]
        try:
            expiry: float | datetime.datetime = float(expiry_str) if unix_time else datetime.datetime.fromisoformat(expiry_str)
        except ValueError:
            err = ValueError("Invalid timestamp format")
            expiry = 0

        if not err and (current_time > expiry):  # type: ignore[operator]
            err = ExpiredTokenError()

        # `key` must be set to some non-empty value when the config cannot be accessed.
        # Otherwise, the `mac` will not be generated.
        if not (key := config.get(secret_key_name, "")):
            key = "default_value"
            err = MissingKeyError()

        mac = ""
        if key:
            mac = hmac.new(key.encode("utf-8"), msg.encode("utf-8"), hashlib.md5).hexdigest()

        result = hmac.compare_digest(mac, digest)
        if err:
            raise err
        return result


class TimedOneTimePassword:
    VALID_MINUTES = 10

    @staticmethod
    def shorten(digest: bytes, length=6) -> str:
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
    def generate(cls, service_ip: str, client_email: str, client_ip: str, ts: int | None = None) -> str:
        seed = config.get("otp_seed")
        ts = ts or int(time.time() // 60)
        payload = f"{service_ip}:{client_email}:{client_ip}:{ts}".encode()
        digest = hmac.new(seed.encode("utf-8"), payload, hashlib.sha256).digest()
        return cls.shorten(digest)

    @staticmethod
    def verify_service(service_ip: str, service_url: str) -> bool:
        """Doesn't work because of VPN"""
        parsed = urlparse(service_url)
        if not parsed.hostname:
            return False
        resolved_ip = socket.gethostbyname(parsed.hostname)
        r = requests.get(service_url, timeout=5)
        return service_url.startswith("https://") and resolved_ip == service_ip and bool(r.json())

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
