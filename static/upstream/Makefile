
JS_SOURCES=			\
    jquery-1.3.2.min.js		\
    jquery.showpassword.min.js	\
    jquery.validate.min.js	\
    jquery.sfx.js

JS_OBJECTS=$(JS_SOURCES:%=js/%)

default: js/vendor.js
    
js/vendor.js: $(JS_OBJECTS) Makefile
	cat $(JS_OBJECTS) > $@
