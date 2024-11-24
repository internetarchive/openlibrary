#!/usr/bin/env python
import web
from openlibrary.core.wikidata import get_wikidata_entity
from openlibrary.config import load_config
import infogami
from infogami import config
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI
import os
from openlibrary.core import db


def walk_redirects(obj, seen):
	seen.add(obj['key'])
	while obj['type']['key'] == '/type/redirect':
		assert obj['location'] != obj['key']
		obj = web.ctx.site.get(obj['location'])
		seen.add(obj['key'])
	return obj

def main(ol_config: str):
	"""
	:param str ol_config: Path to openlibrary.yml file
	"""
	load_config(ol_config)
	infogami._setup()

	password = ''
	try:
		password = open(os.path.expanduser('~/.openlibrary_db_password')).read()
		if password.endswith('\n'):
			password = password[:-1]
	except:
		pass

	d = db.get_db()

	for row in d.query(
		"select * from wikidata"
	):
		e = get_wikidata_entity(row.id)
		ids = e.get_remote_ids()
		if "openlibrary_id" not in ids or not ids["openlibrary_id"]:
			continue
		for key in ids["openlibrary_id"]:
			q = {"type": "/type/author", "key~": key}
			reply = list(web.ctx.site.things(q))
			authors = [web.ctx.site.get(k) for k in reply]
			if any(a.type.key != '/type/author' for a in authors):
				seen: set[dict] = set()
				authors = [walk_redirects(a, seen) for a in authors if a['key'] not in seen]
		print(authors)


if __name__ == "__main__":
	FnToCLI(main).run()