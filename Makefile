#
# Makefile to build css and js files, compile i18n messages and stamp
# version information
#

BUILD=static/build
ACCESS_LOG_FORMAT='%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s"'
COMPONENTS_DIR=openlibrary/components
OSP_DUMP_LOCATION=/solr-updater-data/osp_totals.db


.PHONY: all clean distclean git css js components i18n lint

all: git css js components i18n

css:
	mkdir -p $(BUILD)/css_new
	BUILD_DIR=$(BUILD)/css_new NODE_ENV=production npx webpack --config webpack.config.css.js
	mkdir -p $(BUILD)/css
	rm -rf $(BUILD)/css
	mv $(BUILD)/css_new $(BUILD)/css

js:
	mkdir -p $(BUILD)/js_new
	BUILD_DIR=$(BUILD)/js_new NODE_ENV=production npx webpack
	# This adds FSF licensing for AGPLv3 to our js (for librejs)
	for js in $(BUILD)/js_new/*.js; do \
		echo "// @license magnet:?xt=urn:btih:0b31508aeb0634b347b8270c7bee4d411b5d4109&dn=agpl-3.0.txt AGPL-v3.0" | cat - $$js > /tmp/js && mv /tmp/js $$js; \
		echo "\n// @license-end"  >> $$js; \
	done
	mkdir -p $(BUILD)/js
	rm -rf $(BUILD)/js
	mv $(BUILD)/js_new $(BUILD)/js

components:
	mkdir -p $(BUILD)/components_new
	BUILD_DIR=$(BUILD)/components_new npx vite build -c openlibrary/components/vite.config.mjs
	mkdir -p $(BUILD)/components
	rm -rf $(BUILD)/components
	mv $(BUILD)/components_new $(BUILD)/components


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
	curl -L "https://archive.org/download/2023_openlibrary_osp_counts/osp_totals.db" -o $(OSP_DUMP_LOCATION)
	psql --host db openlibrary -t -c 'select key from thing' | sed 's/ *//' | grep '^/books/' | PYTHONPATH=$(PWD) xargs python openlibrary/solr/update.py --ol-url http://web:8080/ --osp-dump $(OSP_DUMP_LOCATION) --ol-config conf/openlibrary.yml --data-provider=legacy --solr-next
	psql --host db openlibrary -t -c 'select key from thing' | sed 's/ *//' | grep '^/authors/' | PYTHONPATH=$(PWD) xargs python openlibrary/solr/update.py --ol-url http://web:8080/ --osp-dump $(OSP_DUMP_LOCATION) --ol-config conf/openlibrary.yml --data-provider=legacy --solr-next
	psql --host db openlibrary -t -c 'select key from thing' | sed 's/ *//' | grep -E '/(lists|series)/' | PYTHONPATH=$(PWD) xargs python openlibrary/solr/update.py --ol-url http://web:8080/ --osp-dump $(OSP_DUMP_LOCATION) --ol-config conf/openlibrary.yml --data-provider=legacy --solr-next
	PYTHONPATH=$(PWD) python ./scripts/solr_builder/solr_builder/index_subjects.py subject
	PYTHONPATH=$(PWD) python ./scripts/solr_builder/solr_builder/index_subjects.py person
	PYTHONPATH=$(PWD) python ./scripts/solr_builder/solr_builder/index_subjects.py place
	PYTHONPATH=$(PWD) python ./scripts/solr_builder/solr_builder/index_subjects.py time

lint:
	# See the pyproject.toml file for ruff's settings
	python -m ruff check .

test-py:
	pytest . --ignore=infogami --ignore=vendor --ignore=node_modules

test-i18n:
	# Valid locale codes should be added as arguments to validate
	python ./scripts/i18n-messages validate de es fr hr it ja zh

test:
	make test-py && npm run test && make test-i18n
