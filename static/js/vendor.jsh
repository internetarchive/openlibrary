#! /bin/bash
# script for generating vendor.js

DIR=`dirname $0`
OLROOT=$DIR/../..
VENDORJS=$OLROOT/vendor/js

JSMIN="python $VENDORJS/wmd/jsmin.py"

function xcat() {
    cat $1
    printf '\n\n'
}

if [ $1 ]
then
    #v2 javascript
    xcat $VENDORJS/jquery/jquery-1.11.0.min.js
    xcat $VENDORJS/jquery-migrate/jquery-migrate-1.2.1.min.js
    xcat $VENDORJS/slick/slick-1.6.0.min.js
    # For dialog boxes (e.g. add to list)
    xcat $VENDORJS/jquery-ui/jquery-ui-1.12.1.min.js
    xcat $VENDORJS/colorbox/1.5.14.js
else
    #v1 javascript
    xcat $VENDORJS/jquery/jquery-1.3.2.min.js
    xcat $VENDORJS/jquery-ui/jquery-ui-1.7.2.min.js
    xcat $VENDORJS/colorbox/colorbox/jquery.colorbox-min.js
fi

xcat $VENDORJS/jquery-sparkline/jquery.sparkline.min.js
xcat $VENDORJS/jquery-showpassword/jquery.showpassword.min.js
xcat $VENDORJS/jquery-form/jquery.form.js | $JSMIN
xcat $VENDORJS/jquery-validate/jquery.validate.min.js

xcat $VENDORJS/jquery-autocomplete/jquery.autocomplete-modified.js | $JSMIN

xcat $VENDORJS/wmd/jquery.wmd.min.js 

xcat $VENDORJS/flot/excanvas.min.js
xcat $VENDORJS/flot/jquery.flot.min.js
xcat $VENDORJS/flot/jquery.flot.selection.min.js
xcat $VENDORJS/flot/jquery.flot.crosshair.min.js
xcat $VENDORJS/flot/jquery.flot.stack.min.js
xcat $VENDORJS/flot/jquery.flot.pie.min.js

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
function bigCharts() {}
function smallCharts() {}
function passwordMask() {}
function passwordsMask() {}
function feedLoader() {}
function validateForms(){}
END
