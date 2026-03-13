import os
from functools import cached_property


class OLEnv:
    @cached_property
    def OL_EXPOSE_SOLR_INTERNALS_PARAMS(self) -> bool:
        return os.environ.get('OL_EXPOSE_SOLR_INTERNALS_PARAMS') == 'true'


_ol_env = OLEnv()


def get_ol_env() -> OLEnv:
    return _ol_env
