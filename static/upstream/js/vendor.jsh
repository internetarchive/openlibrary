#! /bin/bash
# script for generating vendor.js

DIR=`dirname $0`
OLROOT=$DIR/../../..
VENDORJS=$OLROOT/vendor/js

JSMIN="python $VENDORJS/wmd/jsmin.py"

cat $VENDORJS/colorbox/colorbox/jquery.colorbox-min.js
cat $VENDORJS/jcarousel/lib/jquery.jcarousel.js | $JSMIN
cat $VENDORJS/jquery-sparkline/jquery.sparkline.min.js
cat $VENDORJS/jquery-showpassword/jquery.showpassword.min.js
cat $VENDORJS/jquery-form/jquery.form.js | $JSMIN
cat $VENDORJS/jquery-validate/jquery.validate.min.js

cat $VENDORJS/jquery-flickr/jquery.flickr-1.0-min.js
cat $VENDORJS/jquery-tweet/jquery.tweet.js | $JSMIN

cat $VENDORJS/wmd/jquery.wmd.min.js 

cat $VENDORJS/flot/jquery.flot.min.js
cat $VENDORJS/flot/jquery.flot.selection.min.js
cat $VENDORJS/flot/jquery.flot.crosshair.min.js

# for backward compatability
cat <<END
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
