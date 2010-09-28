#! /bin/bash
# script for generating vendor.js

DIR=`dirname $0`
OLROOT=$DIR/../../..
VENDORJS=$OLROOT/vendor/js

JSMIN="python $VENDORJS/wmd/jsmin.py"

function xcat() {
    cat $1
    echo
    echo
}

xcat $VENDORJS/colorbox/colorbox/jquery.colorbox-min.js
xcat $VENDORJS/jcarousel/lib/jquery.jcarousel.js | $JSMIN
xcat $VENDORJS/jquery-sparkline/jquery.sparkline.min.js
xcat $VENDORJS/jquery-showpassword/jquery.showpassword.min.js
xcat $VENDORJS/jquery-form/jquery.form.js | $JSMIN
xcat $VENDORJS/jquery-validate/jquery.validate.min.js

xcat $VENDORJS/jquery-flickr/jquery.flickr-1.0-min.js
xcat $VENDORJS/jquery-tweet/jquery.tweet.js | $JSMIN

xcat $VENDORJS/jquery-autocomplete/jquery.autocomplete-modified.js | $JSMIN

xcat $VENDORJS/wmd/jquery.wmd.min.js 

xcat $VENDORJS/flot/excanvas.min.js
xcat $VENDORJS/flot/jquery.flot.min.js
xcat $VENDORJS/flot/jquery.flot.selection.min.js
xcat $VENDORJS/flot/jquery.flot.crosshair.min.js

xcat $VENDORJS/json2/json2.js | $JSMIN

# for backward compatability
xcat <<END
function DragDrop() {}
function Resizable() {}
function Selectable() {}
function Sortable() {}
function Accordtion() {}
function Dialog() {}
function Slider() {}
function Tabs() {}
function Datepicker() {}
function Progressbar() {}

function boxPop() {}
function carousels() {}
function bigCharts() {}
function smallCharts() {}
function passwordMask() {}
function passwordsMask() {}
function twitterFeed() {}
function flickrFeed(){}
function feedLoader() {}
function validateForms(){}
END
