#
# Makefile to build css and js files, compile i18n messages and stamp
# version information
#

BUILD=static/build


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

run:
	python setup.py start

restart:
	supervisorctl -c conf/services.ini restart openlibrary

venv:
	virtualenv --no-site-packages env
	./env/bin/pip install -r requirements.txt

bootstrap: venv all
	./env/bin/python scripts/setup_dev_instance.py
    
upgrade: venv all
	./env/bin/python scripts/setup_dev_instance.py --upgrade

