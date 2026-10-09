from dataclasses import dataclass
from datetime import datetime

from openlibrary.core.async_db import class_row, execute, fetch_all, fetch_one


@dataclass(frozen=True, slots=True)
class PatronFeatureInterest:
    """A row from the ``patron_feature_interest`` table."""

    username: str
    feature: str
    created: datetime | None


class PatronFeatureInterestDB:
    TABLENAME = "patron_feature_interest"

    @classmethod
    async def create(cls, username: str, feature: str) -> None:
        """Record a patron's interest in a feature. Idempotent (ON CONFLICT DO NOTHING)."""
        await execute(
            f"INSERT INTO {cls.TABLENAME} (username, feature) VALUES (%(username)s, %(feature)s) ON CONFLICT DO NOTHING",
            {"username": username, "feature": feature},
        )

    @classmethod
    async def exists(cls, username: str, feature: str) -> bool:
        """Check if a patron has already expressed interest in a feature."""
        query = f"SELECT 1 FROM {cls.TABLENAME} WHERE username = %(username)s AND feature = %(feature)s"
        return await fetch_one(query, {"username": username, "feature": feature}) is not None

    @classmethod
    async def select_by_username(cls, username: str) -> list[PatronFeatureInterest]:
        """Get all features a patron has expressed interest in."""
        query = f"SELECT username, feature, created FROM {cls.TABLENAME} WHERE username = %(username)s ORDER BY created DESC"
        return await fetch_all(query, {"username": username}, row_factory=class_row(PatronFeatureInterest))

    @classmethod
    async def select_features_by_username(cls, username: str) -> list[str]:
        """Get just the feature names a patron has expressed interest in."""
        query = f"SELECT feature FROM {cls.TABLENAME} WHERE username = %(username)s ORDER BY created DESC"
        rows = await fetch_all(query, {"username": username})
        return [row["feature"] for row in rows]

    @classmethod
    async def count_by_feature(cls, feature: str) -> int:
        """Count how many patrons have expressed interest in a feature."""
        query = f"SELECT count(*) FROM {cls.TABLENAME} WHERE feature = %(feature)s"
        row = await fetch_one(query, {"feature": feature})
        return row["count"] if row else 0
