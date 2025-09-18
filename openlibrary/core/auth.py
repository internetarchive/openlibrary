import hashlib
import hmac
import time
import requests
from infogami import config
from openlibrary.core import cache

class TimedOneTimePassword:

    VALID_MINUTES = 10
    
    @staticmethod
    def generate(service_ip:str, client_email: str, client_ip: str, ts:int|None = None) -> str:
        seed = config.get("otp_seed")
        ts = ts or int(time.time() // 60)
        payload = f"{service_ip}:{client_email}:{client_ip}:{ts}".encode()
        return hmac.new(seed.encode('utf-8'), payload, hashlib.sha256).hexdigest()

    @staticmethod
    def verify_service(service_ip: str, service_url: str) -> bool:
        try:
            # Is HTTPS, matches IP, valid json response
            return service_url.startswith("https://") and \
                (r := requests.get(service_url, timeout=5)) and \
                r.raw._connection.sock.getpeername()[0] == service_ip and \
                bool(r.json())
        except Exception:
            return False

    @classmethod
    def is_ratelimited(cls, ttl=60, service_ip="", **kwargs):
        def ratelimit_error(key, ttl):
            return {
                "error": "ratelimit",
                "ratelimit": {
                    "ttl": ttl,
                    "key": key
                }
            }

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
        return hmac.compare_digest(otp, expected_otp)

    @classmethod
    def is_valid(cls, client_email, client_ip, service_ip, otp):
        now_minute = int(time.time() // 60)
        for delta in range(cls.VALID_MINUTES):
            minute_ts = now_minute - delta
            if cls.validate(otp, service_ip, client_email, client_ip, minute_ts):
                return True
        return False
            
