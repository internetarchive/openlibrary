
JS_SOURCES=			\
    jquery-1.3.2.min.js		\
    jquery.sfx.js		\
    jquery.validate.min.js

JS_OBJECTS=$(JS_SOURCES:%=js/%)

default: js/vendor.js
    
js/vendor.js: $(JS_OBJECTS)
	cat $(JS_OBJECTS) > $@
	echo "$@?`md5sum $@`" | awk '{print $$1;}'
