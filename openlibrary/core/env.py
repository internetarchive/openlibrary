import os
from functools import cached_property
from typing import Literal, cast

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
    """Which deployment this request is served from, based on the host.

    Drives dev-facing UI cues (favicon, logo badge) so localhost,
    testing.openlibrary.org, and production tabs are distinguishable.
    """
    if deployment_name := os.environ.get("OL_DEPLOYMENT_NAME"):
        return cast(DeploymentName, deployment_name)

    try:
        host = web.ctx.host
    except AttributeError:
        host = ""
    except KeyError:
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
