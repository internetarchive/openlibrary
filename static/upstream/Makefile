
JS_SOURCES=			\
    jquery-1.3.2.min.js		\
    jquery-ui-1.7.2.min.js \
    jquery.others.js		\
    jquery.colorbox-min.js	\
    jquery.jcarousel.pack.js 	\
    jquery.showpassword.min.js	\
    jquery.validate.min.js	\
    jquery.form.js  \
    jquery.tooltip.pack.js  \
    jquery.twitterfeed.js   \
    jquery.flickrfeed.js    \
    jquery.flot.js  \
    jquery.sparklines.js    \
    jquery.markitup.js  \
    jquery.ccopy.js
    

JS_OBJECTS=$(JS_SOURCES:%=js/%)

default: js/vendor.js
    
js/vendor.js: $(JS_OBJECTS) Makefile
	cat $(JS_OBJECTS) > $@
