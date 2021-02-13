import 'jquery';
import 'jquery-migrate';
import 'jquery-validation';
import 'jquery-ui/ui/widgets/dialog';
import 'jquery-ui/ui/widgets/sortable';
import 'jquery-ui/ui/widgets/tabs';
// For dialog boxes (e.g. add to list)
import '../../../../vendor/js/colorbox/1.5.14.js';
// jquery.form#2.36 not on npm, no longer getting worked on
import '../../../../vendor/js/jquery-form/jquery.form.js';
// jquery-autocomplete#1.1 with modified
import '../../../../vendor/js/jquery-autocomplete/jquery.autocomplete-modified.js';
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
// Add $.fn.focusNextInputField
import { closePopup, truncate, cond } from './utils';
import initValidate from './validate';
import '../../../../static/css/js-all.less';
// polyfill Promise support for IE11
import Promise from 'promise-polyfill';
import { confirmDialog, initDialogs } from './dialog';
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
    // expose ol_confirm_dialog method
    $.fn.ol_confirm_dialog = confirmDialog;
    initTabs($('#tabsAddbook,#tabsAddauthor,.tabs:not(.ui-tabs)'));
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
    // conditionally load real time signup functionality based on class in the page
    if (document.getElementsByClassName('olform create validate').length) {
        import('./realtime_account_validation.js')
            .then(module => module.initRealTimeValidation());
    }
    // conditionally load readmore button based on class in the page
    if (document.getElementsByClassName('read-more-button').length) {
        import(/* webpackChunkName: "readmore" */ './readmore.js')
            .then(module => module.initReadMoreButton());
    }
    // conditionally loads Goodreads import based on class in the page
    if (document.getElementsByClassName('import-table').length) {
        import('./goodreads_import.js')
            .then(module => module.initGoodreadsImport());
    }
    // conditionally loads Related Carousels based on class in the page
    if (document.getElementsByClassName('RelatedWorksCarousel').length) {
        import('./carousels_partials.js')
            .then(module => module.initCarouselsPartials());
    }
    // Enable any carousels in the page
    if ($carouselElements.length) {
        import(/* webpackChunkName: "carousel" */ './carousel')
            .then((module) => { module.init($carouselElements);
                $('.slick-slide').each(function () {
                    if ($(this).attr('aria-describedby') != undefined) {
                        $(this).attr('id',$(this).attr('aria-describedby'));
                    }
                });
            })
    }
    if ($('script[type="text/json+graph"]').length > 0) {
        import(/* webpackChunkName: "graphs" */ './graphs')
            .then((module) => module.init());
    }

    if (window.READINGLOG_STATS_CONFIG) {
        import(/* webpackChunkName: "readinglog_stats" */ './readinglog_stats')
            .then(module => module.init(window.READINGLOG_STATS_CONFIG));
    }

    const pageEl = $('#page-barcodescanner');
    if (pageEl.length) {
        import(/* webpackChunkName: "page-barcodescanner" */ './page-barcodescanner')
            .then((module) => module.init());
    }

    if (document.getElementById('modal-link')) {
        import(/* webpackChunkName: "patron_metadata" */ './patron-metadata')
            .then((module) => module.initPatronMetadata());
    }

    if ($('#cboxPrevious').length) {
        $('#cboxPrevious').attr({'aria-label': 'Previous button', 'aria-hidden': 'true'});
    }
    if ($('#cboxNext').length) {
        $('#cboxNext').attr({'aria-label': 'Next button', 'aria-hidden': 'true'});
    }
    if ($('#cboxSlideshow').length) {
        $('#cboxSlideshow').attr({'aria-label': 'Slideshow button', 'aria-hidden': 'true'});
    }

    $(document).on('click', '.slide-toggle', function () {
        $(`#${$(this).attr('aria-controls')}`).slideToggle();
    });

    $('#wikiselect').on('focus', function(){$(this).select();})

    // Functionality for manage.html
    $('.column').sortable({
        connectWith: '.trash'
    });
    $(''.trash').sortable({
        connectWith: '.column'
    });
    $('.column').disableSelection();
    $('.trash').disableSelection();
    $('#topNotice').hide();
});
