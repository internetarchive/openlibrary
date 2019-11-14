import 'jquery';
import 'jquery-migrate';
import 'jquery-validation';
// npm jquery-ui@1.12.1 package does not match the one we have here, so for now we load from vendor
import '../../../../vendor/js/jquery-ui/jquery-ui-1.12.1.min.js';
// For dialog boxes (e.g. add to list)
import '../../../../vendor/js/colorbox/1.5.14.js';
// jquery.form#2.36 not on npm, no longer getting worked on
import '../../../../vendor/js/jquery-form/jquery.form.js';
// jquery-autocomplete#1.1 with modified
import '../../../../vendor/js/jquery-autocomplete/jquery.autocomplete-modified.js';
// unversioned.
import '../../../../vendor/js/wmd/jquery.wmd.js'
import { validateEmail, validatePassword } from './account.js';
import autocompleteInit from './autocomplete';
// Used only by the openlibrary/templates/books/edit/addfield.html template
import addNewFieldInit from './add_new_field';
import automaticInit from './automatic';
import bookReaderInit from './bookreader_direct';
import { ungettext, ugettext,  sprintf } from './i18n';
import addFadeInFunctionsTojQuery from './jquery.customFade';
import jQueryRepeat from './jquery.repeat';
import { enumerate, htmlquote, websafe, foreach, join, len, range } from './jsdef';
import initAnalytics from './ol.analytics';
import init from './ol.js';
import * as Browser from './Browser';
import { commify } from './python';
import { Subject, urlencode, slice } from './subjects';
import Template from './template.js';
// Add $.fn.focusNextInputField, $.fn.ol_confirm_dialog
import { closePopup, truncate, cond } from './utils';
import initValidate from './validate';
import '../../../../static/css/js-all.less';
// polyfill Promise support for IE11
import Promise from 'promise-polyfill';
import initDialogs from './dialog';
import initTabs from './tabs.js';

// Eventually we will export all these to a single global ol, but in the mean time
// we add them to the window object for backwards compatibility.
// closePopup used in openlibrary/templates/covers/saved.html
window.closePopup = closePopup;
window.commify = commify;
window.cond = cond;
window.enumerate = enumerate;
window.foreach = foreach;
window.htmlquote = htmlquote;
window.len = len;
window.range = range;
window.slice = slice;
window.sprintf = sprintf;
window.truncate = truncate;
window.urlencode = urlencode;
window.websafe = websafe;
window._ = ugettext;
window.ungettext = ungettext;
window.uggettext = ugettext;

window.Browser = Browser;
window.Subject = Subject;
window.Template = Template;

// Extend existing prototypes
String.prototype.join = join;

window.jQuery = jQuery;
window.$ = jQuery;

window.Promise = Promise;

// Initialise some things
jQuery(function () {
    const $markdownTextAreas = $('textarea.markdown');
    // Live NodeList is cast to static array to avoid infinite loops
    const $carouselElements = $('.carousel--progressively-enhanced');
    initDialogs();
    initTabs($('#tabsAddbook,#tabsAddauthor'));
    initValidate($);
    autocompleteInit($);
    addNewFieldInit($);
    automaticInit($);
    // wmd editor
    if ($markdownTextAreas.length) {
        import(/* webpackChunkName: "markdown-editor" */ './markdown-editor')
            .then((module) => module.initMarkdownEditor($markdownTextAreas));
    }
    bookReaderInit($);
    addFadeInFunctionsTojQuery($);
    jQueryRepeat($);
    initAnalytics($);
    init($);
    // conditionally load functionality based on what's in the page
    if (document.getElementsByClassName('editions-table--progressively-enhanced').length) {
        import(/* webpackChunkName: "editions-table" */ './editions-table')
            .then(module => module.initEditionsTable());
    }
    // Enable any carousels in the page
    if ($carouselElements.length) {
        import(/* webpackChunkName: "carousel" */ './carousel')
            .then((module) => module.init($carouselElements));
    }
    if ($('script[type="text/json+graph"]').length > 0) {
        import(/* webpackChunkName: "graphs" */ './graphs')
            .then((module) => module.init());
    }
    validateEmail();
    validatePassword();
    $(document).on('click', '.slide-toggle', function () {
        $(`#${$(this).attr('aria-controls')}`).slideToggle();
    });
});
