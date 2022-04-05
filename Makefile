#
# Makefile to build css and js files, compile i18n messages and stamp
# version information
#

BUILD=static/build
ACCESS_LOG_FORMAT='%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s"'
GITHUB_EDITOR_WIDTH=127
FLAKE_EXCLUDE=./.*,vendor/*,node_modules/*
COMPONENTS_DIR=openlibrary/components

# Use python from local env if it exists or else default to python in the path.
PYTHON=$(if $(wildcard env),env/bin/python,python)

.PHONY: all clean distclean git css js components i18n lint

all: git css js components i18n

css: static/css/page-*.less
	mkdir -p $(BUILD)
	parallel --verbose -q npx lessc {} $(BUILD)/{/.}.css --clean-css="--s1 --advanced" ::: $^

js:
	mkdir -p $(BUILD)
	rm -f $(BUILD)/*.js $(BUILD)/*.js.map
	npm run build-assets:webpack
	# This adds FSF licensing for AGPLv3 to our js (for librejs)
	for js in $(BUILD)/*.js; do \
		echo "// @license magnet:?xt=urn:btih:0b31508aeb0634b347b8270c7bee4d411b5d4109&dn=agpl-3.0.txt AGPL-v3.0" | cat - $$js > /tmp/js && mv /tmp/js $$js; \
		echo "\n// @license-end"  >> $$js; \
	done

components: $(COMPONENTS_DIR)/*.vue
	mkdir -p $(BUILD)
	rm -rf $(BUILD)/components
	# Run these silly things one at a time, because they don't support parallelization :(
	parallel --verbose -q --jobs 1 \
		npx vue-cli-service build --no-clean --mode production --dest $(BUILD)/components/production --target wc --name "ol-{/.}" "{}" \
	::: $^

i18n:
	$(PYTHON) ./scripts/i18n-messages compile

git:
	git submodule init
	git submodule sync
	git submodule update

clean:
	rm -rf $(BUILD)

distclean:
	git clean -fdx
	git submodule foreach git clean -fdx

load_sample_data:
	@echo "loading sample docs from openlibrary.org website"
	$(PYTHON) scripts/copydocs.py --list /people/anand/lists/OL1815L
	curl http://localhost:8080/_dev/process_ebooks # hack to show books in returncart

reindex-solr:
	psql --host db openlibrary -t -c 'select key from thing' | sed 's/ *//' | grep '^/books/' | PYTHONPATH=$(PWD) xargs python openlibrary/solr/update_work.py --ol-url http://web:8080/ --ol-config conf/openlibrary.yml --data-provider=legacy
	psql --host db openlibrary -t -c 'select key from thing' | sed 's/ *//' | grep '^/authors/' | PYTHONPATH=$(PWD) xargs python openlibrary/solr/update_work.py --ol-url http://web:8080/ --ol-config conf/openlibrary.yml --data-provider=legacy

lint-diff:
	git diff "$${BASE_BRANCH:-master}" -U0 | ./scripts/flake8-diff.sh

lint:
	# stop the build if there are Python syntax errors or undefined names
	$(PYTHON) -m flake8 . --count --exclude=$(FLAKE_EXCLUDE) --select=E9,F63,F7,F82 --show-source --statistics
ifndef CI
	# exit-zero treats all errors as warnings, only run this in local dev while fixing issue, not CI as it will never fail.
	$(PYTHON) -m flake8 . --count --exclude=$(FLAKE_EXCLUDE) --exit-zero --max-complexity=10 --max-line-length=$(GITHUB_EDITOR_WIDTH) --statistics
endif

test-py:
	pytest . --ignore=tests/integration --ignore=infogami --ignore=vendor --ignore=node_modules

test-i18n:
  # Valid locale codes should be added as arguments to validate
	$(PYTHON) ./scripts/i18n-messages validate de es fr hr ja zh

test:
	make test-py && npm run test && make test-i18n
