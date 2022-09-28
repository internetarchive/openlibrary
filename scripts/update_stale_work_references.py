"""
PYTHONPATH=. python ./scripts/update_stale_work_references.py /olsystem/etc/openlibrary.yml
"""

import web
import infogami
from infogami import config  # noqa: F401
from openlibrary.config import load_config
from openlibrary.core.models import Work
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI
import datetime


def main(ol_config: str, start_offset=0, days=31):
    load_config(ol_config)
    infogami._setup()
    cutoff_date = datetime.datetime.today() - datetime.timedelta(days=days)
    Work.resolve_redirects_bulk(
        start_offset=start_offset,
        cutoff_date=cutoff_date,
    )


if __name__ == '__main__':
    FnToCLI(main).run()
