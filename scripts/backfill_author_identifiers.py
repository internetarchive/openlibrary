"""
Copies all author identifiers from the author's stored Wikidata info into their remote_ids.

To Run:

PYTHONPATH=. python ./scripts/populate_author_identifiers.py /olsystem/etc/openlibrary.yml

(If testing locally, run inside `docker compose exec web bash` and use ./conf/openlibrary.yml)
"""

#!/usr/bin/env python
import web
from openlibrary.core.wikidata import get_wikidata_entity
from openlibrary.config import load_config
import infogami
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI
import os
from openlibrary.core import db


def main(ol_config: str):
    """
    :param str ol_config: Path to openlibrary.yml file
    """
    load_config(ol_config)
    infogami._setup()

    password = ''
    try:
        with pwfile as open(os.path.expanduser('~/.openlibrary_db_password')):
            password = pwfile.read().strip('\n')
    except:
        pass

    # how i fix this lol there's no IP when running from within docker
    web.ctx.ip = '127.0.0.1'

    for row in db.query("select id from wikidata"):
        e = get_wikidata_entity(row.id)
        e.consolidate_remote_author_ids()
        try:
            e.consolidate_remote_author_ids()
        except Exception as err:
            # don't error out if we can't save WD ids to remote IDs. might be a case of identifiers not matching what we have in OL
            # TODO: raise a flag to librarians here?
            print(str(err))
            pass


# Get wikidata for authors who dont have it yet?

if __name__ == "__main__":
    FnToCLI(main).run()
