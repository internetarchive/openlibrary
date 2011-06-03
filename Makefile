
BUILD=static/build

TARGETS = $(BUILD)/all.js $(BUILD)/vendor.js $(BUILD)/all.css

all: .build $(TARGETS)

i18n: 
	./scripts/i18n-messages compile

.build:
	mkdir -p $(BUILD)

$(BUILD)/all.js:
	bash static/js/all.jsh > $@

$(BUILD)/all.css:
	bash static/css/all.cssh > $@

$(BUILD)/vendor.js:
	bash static/js/vendor.jsh > $@

