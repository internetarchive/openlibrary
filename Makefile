#
# Makefile to build css and js files, compile i18n messages and stamp
# version information
#

BUILD=static/build

PYBUNDLE_URL=http://www.archive.org/download/ol_vendor/openlibrary.pybundle
OL_VENDOR=http://www.archive.org/download/ol_vendor
SOLR_VERSION=apache-solr-1.4.0
ACCESS_LOG_FORMAT='%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s"'

# Use python from local env if it exists or else default to python in the path.
PYTHON=$(if $(wildcard env),env/bin/python,python)

.PHONY: all clean distclean git css js i18n lint

all: git css js i18n

css:
	mkdir -p $(BUILD)
	lessc -x static/css/page-admin.less $(BUILD)/page-admin.css
	lessc -x static/css/page-edit.less $(BUILD)/page-edit.css
	lessc -x static/css/page-form.less $(BUILD)/page-form.css
	lessc -x static/css/page-home.less $(BUILD)/page-home.css
	lessc -x static/css/page-plain.less $(BUILD)/page-plain.css
	lessc -x static/css/page-user.less $(BUILD)/page-user.css
	lessc -x static/css/js-all.less $(BUILD)/js-all.css
	lessc -x static/css/page-book-widget.less $(BUILD)/page-book-widget.css
	lessc -x static/css/js-books-edit.less $(BUILD)/js-books-edit.css
	lessc -x static/css/page-design.less $(BUILD)/page-design.css
	lessc -x static/css/page-dev.less $(BUILD)/page-dev.css

js:
	mkdir -p $(BUILD)
	bash static/js/vendor.jsh > $(BUILD)/vendor.js
	bash static/js/vendor.jsh 2 > $(BUILD)/vendor-v2.js
	bash static/js/all.jsh > $(BUILD)/all.js

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

venv:
	@echo "** setting up virtualenv **"
	mkdir -p var/cache/pip
	virtualenv env
	./env/bin/pip install --download-cache var/cache/pip $(OL_VENDOR)/openlibrary.pybundle

install_solr:
	@echo "** installing solr **"
	mkdir -p var/lib/solr var/cache usr/local
	wget -c $(OL_VENDOR)/$(SOLR_VERSION).tgz -O var/cache/$(SOLR_VERSION).tgz
	cd usr/local && tar xzf ../../var/cache/$(SOLR_VERSION).tgz && ln -fs $(SOLR_VERSION) solr

setup_coverstore:
	@echo "** setting up coverstore **"
	$(PYTHON) scripts/setup_dev_instance.py --setup-coverstore

setup_ol: git
	@echo "** setting up openlibrary webapp **"
	$(PYTHON) scripts/setup_dev_instance.py --setup-ol
	@# When bootstrapping, PYTHON will not be env/bin/python as env dir won't be there when make is invoked.
	@# Invoking make again to pick the right PYTHON.
	make all

bootstrap: venv install_solr setup_coverstore setup_ol

run:
	$(PYTHON) scripts/openlibrary-server conf/openlibrary.yml

load_sample_data:
	@echo "loading sample docs from openlibrary.org website"
	$(PYTHON) scripts/copydocs.py --list /people/anand/lists/OL1815L
	curl http://localhost:8080/_dev/process_ebooks # hack to show books in returncart

destroy:
	@echo Destroying the dev instance.
	-dropdb coverstore
	-dropdb openlibrary
	rm -rf var usr env

reindex-solr:
	psql openlibrary -t -c 'select key from thing' | sed 's/ *//' | grep '^/books/' | PYTHONPATH=$(PWD) xargs python openlibrary/solr/update_work.py -s http://0.0.0.0/ -c conf/openlibrary.yml --data-provider=legacy
	psql openlibrary -t -c 'select key from thing' | sed 's/ *//' | grep '^/authors/' | PYTHONPATH=$(PWD) xargs python openlibrary/solr/update_work.py -s http://0.0.0.0/ -c conf/openlibrary.yml --data-provider=legacy

lint:
	# stop the build if there are Python syntax errors or undefined names
	# TODO: Add --select=F821 once the other issues are fixed
	$(PYTHON) -m flake8 . --count --exclude=scripts/20* --select=E901,E999,F822,F823 --show-source --statistics
	# exit-zero treats all errors as warnings.  The GitHub editor is 127 chars wide
	$(PYTHON) -m flake8 . --count --exclude=scripts/20* --exit-zero --max-complexity=10 --max-line-length=127 --statistics

test:
	npm test
	pytest openlibrary/tests openlibrary/mocks openlibrary/olbase openlibrary/plugins openlibrary/utils openlibrary/catalog
