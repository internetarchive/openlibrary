from __future__ import annotations

import os
from dataclasses import dataclass

import httpx
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

router = APIRouter()


def get_base_url() -> str:
    # TODO: do this better
    if os.getenv("LOCAL_DEV") is not None:
        return "http://host.docker.internal:8080"
    elif os.getenv("OL_SENTRY_ENVIRONMENT") == "testing":
        return "https://staging.openlibrary.org"
    else:
        return "https://openlibrary.org"


@dataclass
class HealthCheck:
    name: str
    path: str
    expected_status: int = 200
    must_contain: str | None = None


CHECKS: list[HealthCheck] = [
    HealthCheck("homepage", "/", must_contain="Welcome to Open Library"),
    HealthCheck("login page", "/account/login", must_contain="Log In"),
    HealthCheck("edition search", "/search?q=%22OL23269118M%22&mode=everything", must_contain="adventures in Wonderland"),
    HealthCheck("book page", "/books/OL23269118M/Alice%27s_adventures_in_Wonderland", must_contain="An edition of"),
    HealthCheck("author page", "/authors/OL22098A/Lewis_Carroll", must_contain="Lewis Carroll"),
    HealthCheck("subject page", "/subjects/quotations", must_contain="Quotations | Open Library"),
    HealthCheck("trending page", "/trending/now", must_contain="trending/now | Open Library"),
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
        if check.must_contain:
            content_ok = check.must_contain in response.text

        duration_ms = (time.perf_counter() - start_time) * 1000

        return SmokeTestResult(
            name=check.name,
            path=check.path,
            expected_status=check.expected_status,
            actual_status=actual_status,
            must_contain=check.must_contain,
            passed=status_ok and content_ok,
            duration_ms=round(duration_ms, 2),
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


@router.get("/smoke.json", response_model=SmokeTestsResponse)
async def smoke_tests(request: Request) -> SmokeTestsResponse:
    async with httpx.AsyncClient() as client:
        results = [await run_health_check(check, client) for check in CHECKS]

    passed = sum(1 for r in results if r.passed)
    base_url = get_base_url()
    average_duration_ms = round(sum(r.duration_ms for r in results) / len(results), 2) if results else 0.0

    return SmokeTestsResponse(
        passed=passed,
        total=len(CHECKS),
        base_url=base_url,
        average_duration_ms=average_duration_ms,
        tests=results,
    )
