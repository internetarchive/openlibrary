import datetime
import hashlib
import hmac
import time

from infogami import config


class ExpiredTokenError(Exception):
    pass


class MissingKeyError(Exception):
    pass


class HMACToken:
    @staticmethod
    def verify(digest: str, msg: str, secret_key_name: str, delimiter: str = "|", unix_time=False) -> bool:
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

        current_time = time.time() if unix_time else datetime.datetime.now(datetime.UTC)
        expiry_str = msg.rsplit(delimiter, maxsplit=1)[-1]
        try:
            expiry = float(expiry_str) if unix_time else datetime.datetime.fromisoformat(expiry_str)
        except ValueError:
            err = ValueError("Invalid timestamp format")
            expiry = 0

        if not err and (current_time > expiry):
            err = ExpiredTokenError()

        # `key` must be set to some non-empty value when the config cannot be accessed.
        # Otherwise, the `mac` will not be generated.
        if not (key := config.get(secret_key_name, '')):
            key = 'default_value'
            err = MissingKeyError()

        mac = ''
        if key:
            mac = hmac.new(
                key.encode('utf-8'), msg.encode('utf-8'), hashlib.md5
            ).hexdigest()

        result = hmac.compare_digest(mac, digest)
        if err:
            raise err
        return result
