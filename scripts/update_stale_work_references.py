"""
PYTHONPATH=. python ./scripts/update_stale_work_references.py /olsystem/etc/openlibrary.yml
"""

import infogami
from infogami import config  # noqa: F401 side effects may be needed
from openlibrary.config import load_config
from openlibrary.core.models import Work
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI


def main(ol_config: str, days=1, skip=7):
    load_config(ol_config)
    infogami._setup()
    Work.resolve_redirects_bulk(
        batch_size=1000, days=days, grace_period_days=skip, test=False
    )


if __name__ == '__main__':
    FnToCLI(main).run()
