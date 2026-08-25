#
# Makefile to build css and js files, compile i18n messages and stamp
# version information
#

BUILD=static/build
ACCESS_LOG_FORMAT='%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s"'
COMPONENTS_DIR=openlibrary/components
OSP_DUMP_LOCATION=/solr-updater-data/osp_totals.db


.PHONY: all clean distclean git css js components lit-components icons i18n lint frontend

all: git css js components icons lit-components i18n

frontend: css js components icons lit-components

node_modules: package-lock.json package.json
ifeq ($(LOCAL_DEV),true)
	npm ci --no-audit --no-fund
endif

css: node_modules
	mkdir -p $(BUILD)/css_new
	BUILD_DIR=$(BUILD)/css_new npx vite build -c vite-css.config.mjs
	mkdir -p $(BUILD)/css
	rm -rf $(BUILD)/css
	mv $(BUILD)/css_new $(BUILD)/css

js: node_modules
	rm -rf $(BUILD)/js_new
	mkdir -p $(BUILD)/js_new
	BUILD_DIR=$(BUILD)/js_new npx vite build -c vite-js.config.mjs
	BUILD_DIR=$(BUILD)/js_new IIFE_ENTRY=sw npx vite build -c vite-js-iife.config.mjs
	BUILD_DIR=$(BUILD)/js_new IIFE_ENTRY=partnerLib npx vite build -c vite-js-iife.config.mjs
	mkdir -p $(BUILD)/js
	rm -rf $(BUILD)/js
	mv $(BUILD)/js_new $(BUILD)/js

components: node_modules
	mkdir -p $(BUILD)/components_new
	BUILD_DIR=$(BUILD)/components_new npx vite build -c openlibrary/components/vite.config.mjs
	mkdir -p $(BUILD)/components
	rm -rf $(BUILD)/components
	mv $(BUILD)/components_new $(BUILD)/components

lit-components: node_modules icons
	# Regenerate the Custom Elements Manifest (committed; consumed by /developers/design)
	npx cem analyze
	mkdir -p $(BUILD)/lit-components_new
	BUILD_DIR=$(BUILD)/lit-components_new NODE_ENV=production npx vite build -c openlibrary/components/vite-lit.config.mjs
	mkdir -p $(BUILD)/lit-components
	rm -rf $(BUILD)/lit-components
	mv $(BUILD)/lit-components_new $(BUILD)/lit-components

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
	python -m ruff check .

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
