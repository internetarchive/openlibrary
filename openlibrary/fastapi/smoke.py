from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from openlibrary.core import cache

router = APIRouter()


def get_base_url() -> str:
    # TODO: do this better
    if os.getenv("LOCAL_DEV") is not None:
        return "http://host.docker.internal:8080"
    else:
        return "https://testing.openlibrary.org"


@dataclass
class HealthCheck:
    name: str
    path: str
    expected_status: int = 200
    must_contain: str | None = None


CHECKS: list[HealthCheck] = [
    HealthCheck("homepage", "/", must_contain="Welcome to Open Library"),
    HealthCheck("login page", "/account/login", must_contain="Log In"),
    HealthCheck("edition search", "/search?q=%22OL23269118M%22&mode=everything", must_contain="ventures in Wonderland"),
    HealthCheck("work page", "/works/OL54120W/The_wit_wisdom_of_Mark_Twain", must_contain="Mark Twain"),
    HealthCheck("edition page", "/books/OL23269118M/Alice%27s_adventures_in_Wonderland", must_contain="An edition of"),
    HealthCheck("author page", "/authors/OL22098A/Lewis_Carroll", must_contain="Lewis Carroll"),
    HealthCheck("subject page", "/subjects/quotations", must_contain="Quotations | Open Library"),
    HealthCheck("trending page", "/trending/now", must_contain="readers from the community"),
    HealthCheck("lists page", "/lists", must_contain="Lists | Open Library"),
    # Endpoints
    HealthCheck("health endpoint", "/health", must_contain="OK"),
    HealthCheck("search endpoint", "/search.json?q=OL23269118M", must_contain="Lewis Carroll"),
]


class SmokeTestResult(BaseModel):
    name: str
    path: str
    expected_status: int
    actual_status: int | None = None
    must_contain: str | None = None
    passed: bool
    duration_ms: float
    error: str | None = None


class SmokeTestsResponse(BaseModel):
    passed: int = Field(description="Number of tests that passed")
    total: int = Field(description="Total number of tests")
    base_url: str = Field(description="Base URL used for smoke tests")
    average_duration_ms: float = Field(description="Average response time across all tests in milliseconds")
    timestamp: str = Field(description="ISO 8601 timestamp of when the tests were run")
    tests: list[SmokeTestResult] = Field(description="Individual test results")


async def run_health_check(check: HealthCheck, client: httpx.AsyncClient) -> SmokeTestResult:
    import time

    start_time = time.perf_counter()
    base_url = get_base_url()

    try:
        url = f"{base_url}{check.path}"
        response = await client.get(url, follow_redirects=True)

        actual_status = response.status_code
        status_ok = actual_status == check.expected_status

        content_ok = True
        error = None
        if check.must_contain:
            content_ok = check.must_contain in response.text
            if not content_ok:
                error = f"Response does not contain expected text: {check.must_contain}"

        duration_ms = (time.perf_counter() - start_time) * 1000

        return SmokeTestResult(
            name=check.name,
            path=check.path,
            expected_status=check.expected_status,
            actual_status=actual_status,
            must_contain=check.must_contain,
            passed=status_ok and content_ok,
            duration_ms=round(duration_ms, 2),
            error=error,
        )
    except httpx.HTTPError as e:
        duration_ms = (time.perf_counter() - start_time) * 1000
        return SmokeTestResult(
            name=check.name,
            path=check.path,
            expected_status=check.expected_status,
            actual_status=None,
            must_contain=check.must_contain,
            passed=False,
            duration_ms=round(duration_ms, 2),
            error=str(e),
        )


@cache.memoize(engine="memcache", key="smoke_tests", expires=300, cacheable=lambda k, v: True)
async def _run_smoke_tests() -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        results = [await run_health_check(check, client) for check in CHECKS]

    passed = sum(1 for r in results if r.passed)
    base_url = get_base_url()
    average_duration_ms = round(sum(r.duration_ms for r in results) / len(results), 2) if results else 0.0

    return SmokeTestsResponse(
        passed=passed,
        total=len(CHECKS),
        base_url=base_url,
        average_duration_ms=average_duration_ms,
        timestamp=datetime.now(UTC).isoformat(),
        tests=results,
    ).model_dump()


@router.get("/smoke.json", include_in_schema=False)
async def smoke_tests(request: Request):
    return await _run_smoke_tests()
