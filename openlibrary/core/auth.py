import hashlib
import hmac
import time
from openlibrary.core import cache
from openlibrary.core.lending import config_otp_seed as OTP_SEED

class TimedOneTimePassword:

    VALID_MINUTES = 10
    
    @staticmethod
    def generate(email: str, ip: str, client: str, ts=None) -> str:
        ts = ts or int(time.time() // 60)
        payload = f"{client}:{email}:{ip}:{ts}".encode()
        return hmac.new(OTP_SEED.encode('utf-8'), payload, hashlib.sha256).hexdigest()

    @classmethod
    def is_ratelimit(cls, ttl=60, client="", **kwargs):
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
            cache_key = f"otp-client:{client}:{key}:{value}"
            if not mc.add(cache_key, 1, expires=ttl):
                return ratelimit_error(cache_key, ttl)

        # Limit globally to 3 attempts per email and ip per / ttl
        for key, value in kwargs.items():
            cache_key = f"otp-global:{key}:{value}"
            count = mc.incr(cache_key) if mc.get(cache_key)
            if mc.get(cache_key):
                count = mc.incr(cache_key)
            else:
                mc.set(cache_key, 1, expires=ttl)
                count = 1
            if count > 3:
                return ratelimit_error(cache_key, ttl)


    @classmethod
    def validate(cls, otp, email, ip, client, ts):
        expected_otp = cls.generate(email, ip, client, ts)
        return hmac.compare_digest(otp, expected_otp)

    @classmethod
    def is_valid(cls, email, ip, client, otp):
        now_minute = int(time.time() // 60)
        for delta in range(cls.VALID_MINUTES):
            ts = now_minute - delta
            if cls.validate(otp, email, ip, client, ts):
                return True
        return False
            
