import os
from functools import cached_property

import web


class OLEnv:
    @cached_property
    def OL_EXPOSE_SOLR_INTERNALS_PARAMS(self) -> bool:
        return os.environ.get("OL_EXPOSE_SOLR_INTERNALS_PARAMS") == "true"

    @cached_property
    def LOCAL_DEV(self) -> bool:
        return os.environ.get("LOCAL_DEV") == "true"


def get_deployment_name() -> str:
    """Which deployment this request is served from, based on the host.

    Drives dev-facing UI cues (favicon, logo badge) so localhost,
    testing.openlibrary.org, and production tabs are distinguishable.
    """
    match web.ctx.host:
        case "openlibrary.org" | "www.openlibrary.org":
            return "production"
        case "testing.openlibrary.org":
            return "testing"
        case _:
            return "development"


_ol_env = OLEnv()


def get_ol_env() -> OLEnv:
    return _ol_env
