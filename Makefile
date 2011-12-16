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

.PHONY: all clean distclean git css js i18n

all: git css js i18n

css:
	mkdir -p $(BUILD)
	bash static/css/all.cssh > $(BUILD)/all.css

js: 
	mkdir -p $(BUILD)
	bash static/js/vendor.jsh > $(BUILD)/vendor.js
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
	mkdir -p var/cache/pip
	virtualenv --no-site-packages env
	./env/bin/pip install --download-cache var/cache/pip $(OL_VENDOR)/openlibrary.pybundle

install_solr: 
	mkdir -p var/lib/solr var/cache usr/local
	wget -c $(OL_VENDOR)/$(SOLR_VERSION).tgz -O var/cache/$(SOLR_VERSION).tgz
	cd usr/local && tar xzf ../../var/cache/$(SOLR_VERSION).tgz && ln -fs $(SOLR_VERSION) solr

setup_coverstore:
	$(PYTHON) scripts/setup_dev_instance.py --setup-coverstore

setup_ol: all
	$(PYTHON) scripts/setup_dev_instance.py --setup-ol

bootstrap: venv install_solr setup_coverstore setup_ol

run:
	env/bin/python scripts/openlibrary-server conf/openlibrary.yml --gunicorn -w 2 -b 0.0.0.0:8080 -t 300 --access-logfile=/dev/tty --access-logformat=$(ACCESS_LOG_FORMAT)

