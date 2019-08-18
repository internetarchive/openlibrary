import { validateEmail, validatePassword } from './account.js';
import autocompleteInit from './autocomplete';
import addNewFieldInit from './add_new_field';
import automaticInit from './automatic';
import { getAvailabilityV2,
    updateBookAvailability, updateWorkAvailability } from './availability';
import bookReaderInit from './bookreader_direct';
import Carousel from './carousels';
import { ungettext, ugettext,  sprintf } from './i18n';
// Load jQuery plugins
import './jquery.columnize';
import './jquery.dataTables';
import './jquery.hoverIntent';
import './jquery.jTruncate';
import addFadeInFunctionsTojQuery from './jquery.customFade';
import fadeToggle from './jquery.fadeToggle';
import jQueryRepeat from './jquery.repeat';
import './jquery.scrollTo';
import { enumerate, htmlquote, websafe, foreach, join, len, range } from './jsdef';
// Note this import will also load various jQuery plugins.
// (jQuery.ScrollTo, jquery.hoverIntent, jquery.dataTables, dataTableExt,
// highlight, removeHighlight, jTruncate, columnize)
import { plot_minigraph, plot_tooltip_graph } from './plot';
import removeHighlight from './removeHighlight';
import highlight from './highlight';
import initAnalytics from './ol.analytics';
// Also pulls in jQuery.fn.exists
import init, { closePop, bookCovers, isScrolledIntoView } from './ol.js';
import * as Browser from './Browser';
import { commify } from './python';
import { Subject, urlencode, renderTag, slice } from './subjects';
import Template from './template.js';
// Add $.fn.focusNextInputField, $.fn.ol_confirm_dialog, $.fn.tap
import { closePopup, initShowPasswords, truncate, cond } from './utils';
import initValidate from './validate';
import '../../../../static/css/js-all.less';

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

jQuery.fn.exists = function(){return jQuery(this).length>0;}
jQuery.fn.removeHighlight = removeHighlight;
jQuery.fn.highlight = highlight;
jQuery.fn.fadeToggle = fadeToggle;

// Initialise some things
$(function () {
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
});
