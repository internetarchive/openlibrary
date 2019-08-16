import 'jquery';
import 'jquery-migrate';
// Slick#1.6.0 is not on npm
import '../../../../vendor/js/slick/slick-1.6.0.min.js';
// npm jquery-ui@1.12.1 package does not match the one we have here, so for now we load from vendor
import '../../../../vendor/js/jquery-ui/jquery-ui-1.12.1.min.js';
// For dialog boxes (e.g. add to list)
import '../../../../vendor/js/colorbox/1.5.14.js';
// jquery-show-password#1.0 not on npm, no longer getting worked on
import '../../../../vendor/js/jquery-showpassword/jquery.showpassword.js';
// jquery.form#2.36 not on npm, no longer getting worked on
import '../../../../vendor/js/jquery-form/jquery.form.js';
// jquery-validate#1.6 not on npm
import '../../../../vendor/js/jquery-validate/jquery.validate.js';
// jquery-autocomplete#1.1 with modified
import '../../../../vendor/js/jquery-autocomplete/jquery.autocomplete-modified.js';
// unversioned.
import '../../../../vendor/js/wmd/jquery.wmd.js'
// jquery-flot 0.7.0
import '../../../../vendor/js/flot/jquery.flot.js';
import '../../../../vendor/js/flot/jquery.flot.selection.js';
import '../../../../vendor/js/flot/jquery.flot.crosshair.js';
import '../../../../vendor/js/flot/jquery.flot.stack.js';
import '../../../../vendor/js/flot/jquery.flot.pie.js';
import { validateEmail, validatePassword } from './account.js';
import autocompleteInit from './autocomplete';
import addNewFieldInit from './add_new_field';
import automaticInit from './automatic';
import { getAvailabilityV2,
    updateBookAvailability, updateWorkAvailability } from './availability';
import bookReaderInit from './bookreader_direct';
import Carousel from './carousels';
import { ungettext, ugettext,  sprintf } from './i18n';
import addFadeInFunctionsTojQuery from './jquery.customFade';
import jQueryRepeat from './jquery.repeat';
import './jquery.scrollTo';
import { enumerate, htmlquote, websafe, foreach, join, len, range } from './jsdef';
import { plot_minigraph, plot_tooltip_graph } from './plot';
import initAnalytics from './ol.analytics';
import init, { closePop, bookCovers, isScrolledIntoView } from './ol.js';
import * as Browser from './Browser';
import { commify } from './python';
import { Subject, urlencode, renderTag, slice } from './subjects';
import Template from './template.js';
// Add $.fn.focusNextInputField, $.fn.ol_confirm_dialog, $.fn.tap
import { closePopup, initShowPasswords, truncate, cond } from './utils';
import initValidate from './validate';
import '../../../../static/css/js-all.less';
// polyfill Promise support for IE11
import Promise from 'promise-polyfill';

// Eventually we will export all these to a single global ol, but in the mean time
// we add them to the window object for backwards compatibility.
window.bookCovers = bookCovers;
window.closePop = closePop;
window.closePopup = closePopup;
window.commify = commify;
window.cond = cond;
window.enumerate = enumerate;
window.foreach = foreach;
window.getAvailabilityV2 = getAvailabilityV2;
window.isScrolledIntoView = isScrolledIntoView;
window.htmlquote = htmlquote;
window.len = len;
window.plot_tooltip_graph = plot_tooltip_graph;
window.plot_minigraph = plot_minigraph;
window.range = range;
window.renderTag = renderTag;
window.slice = slice;
window.sprintf = sprintf;
window.truncate = truncate;
window.updateBookAvailability = updateBookAvailability;
window.updateWorkAvailability = updateWorkAvailability;
window.urlencode = urlencode;
window.validateEmail = validateEmail;
window.validatePassword = validatePassword;
window.websafe = websafe;
window._ = ugettext;
window.ungettext = ungettext;
window.uggettext = ugettext;

window.Browser = Browser;
window.Carousel = Carousel;
window.Subject = Subject;
window.Template = Template;

// Extend existing prototypes
String.prototype.join = join;

window.jQuery = jQuery;
window.$ = jQuery;

window.Promise = Promise;

// Initialise some things
jQuery(function () {
    initValidate($);
    autocompleteInit($);
    addNewFieldInit($);
    automaticInit($);
    bookReaderInit($);
    addFadeInFunctionsTojQuery($);
    jQueryRepeat($);
    initAnalytics($);
    init($);
    initShowPasswords($);
    // conditionally load functionality based on what's in the page
    if (document.getElementsByClassName('editions-table--progressively-enhanced').length) {
        import(/* webpackChunkName: "editions-table" */ './editions-table')
            .then(module => module.initEditionsTable());
    }
});
