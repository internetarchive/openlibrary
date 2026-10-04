import os
from functools import cached_property
from typing import Literal

import web


class OLEnv:
    @cached_property
    def OL_EXPOSE_SOLR_INTERNALS_PARAMS(self) -> bool:
        return os.environ.get("OL_EXPOSE_SOLR_INTERNALS_PARAMS") == "true"

    @cached_property
    def LOCAL_DEV(self) -> bool:
        return os.environ.get("LOCAL_DEV") == "true"


DeploymentName = Literal["development", "testing", "production"]


def get_deployment_name() -> DeploymentName:
    """Which deployment serves this process.

    Returns the OL_DEPLOYMENT_NAME environment variable (set per deployment
    in the compose files) when present, otherwise falls back to the request
    host, and finally to "development" when there is no request context
    (e.g. at application startup).

    Drives dev-facing UI cues (favicon, logo badge) so localhost,
    testing.openlibrary.org, and production tabs are distinguishable.
    """
    if deployment_name := os.environ.get("OL_DEPLOYMENT_NAME"):
        match deployment_name:
            case "development" | "testing" | "production":
                return deployment_name
            case _:
                raise ValueError(f'Invalid OL_DEPLOYMENT_NAME {deployment_name!r}; expected "development", "testing", or "production"')

    try:
        host = web.ctx.host
    except AttributeError, KeyError:
        host = ""

    match host:
        case "openlibrary.org" | "www.openlibrary.org":
            return "production"
        case "testing.openlibrary.org":
            return "testing"
        case _:
            return "development"


_ol_env = OLEnv()


def get_ol_env() -> OLEnv:
    return _ol_env
