
BUILD=static/build

.PHONY: all clean distclean

all: 
	mkdir -p $(BUILD)
	git submodule init
	git submodule sync
	git submodule update
	python ./scripts/i18n-messages compile
	bash static/js/vendor.jsh > $(BUILD)/vendor.js
	bash static/js/all.jsh > $(BUILD)/all.js
	bash static/css/all.cssh > $(BUILD)/all.css

clean:
	rm -rf $(BUILD)

distclean:
	git clean -fdx 
	git submodule foreach git clean -fdx
