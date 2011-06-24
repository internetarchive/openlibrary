
BUILD=static/build

TARGETS = $(BUILD)/all.js $(BUILD)/vendor.js $(BUILD)/all.css

.PHONY: $(TARGETS)

all: .build $(TARGETS)

i18n: 
	./scripts/i18n-messages compile

.build:
	mkdir -p $(BUILD)

$(BUILD)/all.js: static/js/all.jsh
	bash static/js/all.jsh > $@

$(BUILD)/all.css: static/css/all.cssh
	bash static/css/all.cssh > $@

$(BUILD)/vendor.js: static/js/vendor.jsh
	bash static/js/vendor.jsh > $@

clean:
	rm -rf $(TARGETS)
