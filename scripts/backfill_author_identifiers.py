"""
Copies all author identifiers from the author's stored Wikidata info into their remote_ids.

To Run:

PYTHONPATH=. python ./scripts/populate_author_identifiers.py /olsystem/etc/openlibrary.yml

(If testing locally, run inside `docker compose exec web bash` and use ./conf/openlibrary.yml)
"""

#!/usr/bin/env python
import infogami
import web
from openlibrary.config import load_config
from openlibrary.core import db
from openlibrary.core.wikidata import get_wikidata_entity
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI


def main(ol_config: str):
    """
    :param str ol_config: Path to openlibrary.yml file
    """
    load_config(ol_config)
    infogami._setup()

    # how i fix this lol there's no IP when running from within docker
    web.ctx.ip = '127.0.0.1'

    for row in db.query("select id from wikidata"):
        e = get_wikidata_entity(row.id)
        e.consolidate_remote_author_ids()


# Get wikidata for authors who dont have it yet?

if __name__ == "__main__":
    FnToCLI(main).run()
