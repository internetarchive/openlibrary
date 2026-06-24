from __future__ import annotations

import os
from functools import cached_property


class OLEnv:
    @cached_property
    def OL_EXPOSE_SOLR_INTERNALS_PARAMS(self) -> bool:
        return os.environ.get("OL_EXPOSE_SOLR_INTERNALS_PARAMS") == "true"

    @cached_property
    def LOCAL_DEV(self) -> bool:
        return os.environ.get("LOCAL_DEV") == "true"


_ol_env = OLEnv()


def get_ol_env() -> OLEnv:
    return _ol_env
