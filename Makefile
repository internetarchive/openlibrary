#
# Makefile to build css and js files, compile i18n messages and stamp
# version information
#

BUILD=static/build
ACCESS_LOG_FORMAT='%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s"'
COMPONENTS_DIR=openlibrary/components
OSP_DUMP_LOCATION=/solr-updater-data/osp_totals.db


.PHONY: all clean distclean git css js components lit-components icons i18n lint frontend

all: git frontend i18n

frontend: node_modules icons
	# Regenerate the Custom Elements Manifest (committed; consumed by /developers/design)
	npx cem analyze
	node scripts/vite/build.mjs

node_modules: package-lock.json package.json
ifeq ($(LOCAL_DEV),true)
	npm ci --no-audit --no-fund
endif

css: node_modules
	node scripts/vite/build.mjs --only css

js: node_modules
	node scripts/vite/build.mjs --only js

components: node_modules icons
	# Regenerate the Custom Elements Manifest (committed; consumed by /developers/design)
	npx cem analyze
	node scripts/vite/build.mjs --only components

lit-components: components

icons:
	# Build the icon sprite and the Lit glyph module from static/icons/src/.
	# Neither is committed. No node_modules prerequisite — the script is pure Node.
	node scripts/build_icon_sprite.mjs

i18n:
	python ./scripts/i18n-messages compile

git:
	git submodule init
	git submodule sync
	git submodule update

clean:
	rm -rf $(BUILD)

distclean:
	git clean -fdx
	git submodule foreach git clean -fdx


reindex-solr:
    # Keep link in sync with ol-solr-updater-start and Jenkinsfile
	curl -C - -L "https://archive.org/download/2023_openlibrary_osp_counts/osp_totals.db" -o $(OSP_DUMP_LOCATION)
	psql --host db openlibrary -t -c 'select key from thing' | sed 's/ *//' | grep '^/books/' | xargs python openlibrary/solr/update.py --ol-url http://web:8080/ --osp-dump $(OSP_DUMP_LOCATION) --ol-config conf/openlibrary.yml --solr-next
	psql --host db openlibrary -t -c 'select key from thing' | sed 's/ *//' | grep '^/authors/' | xargs python openlibrary/solr/update.py --ol-url http://web:8080/ --osp-dump $(OSP_DUMP_LOCATION) --ol-config conf/openlibrary.yml --solr-next
	psql --host db openlibrary -t -c 'select key from thing' | sed 's/ *//' | grep -E '/(lists|series)/' | xargs python openlibrary/solr/update.py --ol-url http://web:8080/ --osp-dump $(OSP_DUMP_LOCATION) --ol-config conf/openlibrary.yml --solr-next
	parallel -j4 python ./scripts/solr_builder/solr_builder/index_subjects.py ::: subject person place time

lint:
	# See the pyproject.toml file for ruff's settings
	uv run --with-requirements requirements_test.txt ruff check .

PYTEST_ARGS ?= . --doctest-modules

test-py:
	pytest $(PYTEST_ARGS)

test-py-uv:
	uv run --with-requirements requirements_test.txt pytest $(PYTEST_ARGS)

test-i18n:
	# Valid locale codes should be added as arguments to validate
	python ./scripts/i18n-messages validate de es fr hr it ja zh

test:
	make test-py && npm run test && make test-i18n
