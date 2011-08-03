#
# Makefile to build css and js files, compile i18n messages and stamp
# version information
#

BUILD=static/build

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
