import 'jquery';
import 'jquery-validation';
import 'jquery-ui/ui/widgets/dialog';
import 'jquery-ui/ui/widgets/autocomplete';
// For dialog boxes (e.g. add to list)
import 'jquery-colorbox';
// jquery.form#2.36 not on npm, no longer getting worked on
import '../../../../vendor/js/jquery-form/jquery.form.js';
import autocompleteInit from './autocomplete';
// Used only by the openlibrary/templates/books/edit/addfield.html template
import addNewFieldInit from './add_new_field';
import automaticInit from './automatic';
import bookReaderInit from './bookreader_direct';
import { ungettext, ugettext,  sprintf } from './i18n';
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

// This to the best of our knowledge needs to be run synchronously,
// because it sends the initial pageview to analytics.
initAnalytics();

// Initialise some things
jQuery(function () {
    // conditionally load polyfill for <details> tags (IE11)
    // See http://diveintohtml5.info/everything.html#details
    if (!('open' in document.createElement('details'))) {
        import(/* webpackChunkName: "details-polyfill" */ 'details-polyfill');
    }

    const $markdownTextAreas = $('textarea.markdown');
    // Live NodeList is cast to static array to avoid infinite loops
    const $carouselElements = $('.carousel--progressively-enhanced');
    const $tabs = $('#tabsAddbook,#tabsAddauthor,.tabs:not(.ui-tabs)');

    initDialogs();
    // expose ol_confirm_dialog method
    $.fn.ol_confirm_dialog = confirmDialog;

    if ($tabs.length) {
        import(/* webpackChunkName: "tabs" */ './tabs')
            .then((module) => module.initTabs($tabs));
    }

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
    jQueryRepeat($);
    init($);
    // conditionally load functionality based on what's in the page
    if (document.getElementsByClassName('editions-table--progressively-enhanced').length) {
        import(/* webpackChunkName: "editions-table" */ './editions-table')
            .then(module => module.initEditionsTable());
    }

    const edition = document.getElementById('tabsAddbook');
    const autocompleteAuthor = document.querySelector('.multi-input-autocomplete--author');
    const addRowButton = document.getElementById('add_row_button');
    const roles = document.querySelector('#roles');
    const identifiers = document.querySelector('#identifiers');
    const classifications = document.querySelector('#classifications');
    const autocompleteLanguage = document.querySelector('.multi-input-autocomplete--language');
    const autocompleteWorks = document.querySelector('.multi-input-autocomplete--works');
    const excerpts = document.getElementById('excerpts');
    const links = document.getElementById('links');

    // conditionally load for user edit page
    if (
        edition ||
        autocompleteAuthor || addRowButton || roles || identifiers || classifications ||
        autocompleteLanguage || autocompleteWorks || excerpts || links
    ) {
        import(/* webpackChunkName: "user-website" */ './edit')
            .then(module => {
                if (edition) {
                    module.initEdit();
                }
                if (addRowButton) {
                    module.initEditRow();
                }
                if (excerpts) {
                    module.initEditExcerpts();
                }
                if (links) {
                    module.initEditLinks();
                }
                if (autocompleteAuthor) {
                    module.initAuthorMultiInputAutocomplete();
                }
                if (roles) {
                    module.initRoleValidation();
                }
                if (identifiers) {
                    module.initIdentifierValidation();
                }
                if (classifications) {
                    module.initClassificationValidation();
                }
                if (autocompleteLanguage) {
                    module.initLanguageMultiInputAutocomplete();
                }
                if (autocompleteWorks) {
                    module.initWorksMultiInputAutocomplete();
                }
            });
    }

    // conditionally load for author merge page
    const mergePageElement = document.querySelector('#author-merge-page');
    const preMergePageElement = document.getElementById('preMerge');
    if (mergePageElement || preMergePageElement) {
        import(/* webpackChunkName: "merge" */ './merge')
            .then(module => {
                if (mergePageElement) {
                    module.initAuthorMergePage();
                }
                if (preMergePageElement) {
                    module.initAuthorView();
                }
            });
    }

    // conditionally load real time signup functionality based on class in the page
    if (document.getElementsByClassName('olform create validate').length) {
        import(/* webpackChunkName: "realtime-account-validation" */'./realtime_account_validation.js')
            .then(module => module.initRealTimeValidation());
    }
    // conditionally load readmore button based on class in the page
    if (document.getElementsByClassName('read-more-button').length) {
        import(/* webpackChunkName: "readmore" */ './readmore.js')
            .then(module => module.initReadMoreButton());
    }
    // conditionally loads Goodreads import based on class in the page
    if (document.getElementsByClassName('import-table').length) {
        import(/* webpackChunkName: "goodreads-import" */'./goodreads_import.js')
            .then(module => module.initGoodreadsImport());
    }
    // conditionally loads Related Carousels based on class in the page
    if (document.getElementsByClassName('RelatedWorksCarousel').length) {
        import(/* webpackChunkName: "carousels-partials" */'./carousels_partials.js')
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
        import(/* webpackChunkName: "readinglog-stats" */ './readinglog_stats')
            .then(module => module.init(window.READINGLOG_STATS_CONFIG));
    }

    const pageEl = $('#page-barcodescanner');
    if (pageEl.length) {
        import(/* webpackChunkName: "page-barcodescanner" */ './page-barcodescanner')
            .then((module) => module.init());
    }

    if (document.getElementsByClassName('modal-link').length) {
        import(/* webpackChunkName: "patron-metadata" */ './patron-metadata')
            .then((module) => module.initPatronMetadata());
    }

    const manageCoversElement = document.getElementsByClassName('manageCovers').length;
    const addCoversElement = document.getElementsByClassName('imageIntro').length;
    const saveCoversElement = document.getElementsByClassName('imageSaved').length;

    if (addCoversElement || manageCoversElement || saveCoversElement) {
        import(/* webpackChunkName: "covers" */ './covers')
            .then((module) => {
                if (manageCoversElement) {
                    module.initCoversChange();
                }
                if (addCoversElement) {
                    module.initCoversAddManage();
                }
                if (saveCoversElement) {
                    module.initCoversSaved();
                }
            });
    }

    if (document.getElementById('addbook')) {
        import(/* webpackChunkName: "add-book" */ './add-book')
            .then(module => module.initAddBookImport());
    }

    if (document.getElementById('adminLinks')) {
        import(/* webpackChunkName: "admin" */ './admin')
            .then((module) => module.initAdmin());
    }

    if (document.getElementById('searchFacets')) {
        import(/* webpackChunkName: "search" */ './search')
            .then((module) => module.initSearchFacets());
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

    $('#wikiselect').on('focus', function(){$(this).trigger('select');})

    // Open one dropdown at a time.
    $(document).on('click', function (event) {
        const $openMenus = $('.header-dropdown details[open]').parents('.header-dropdown');
        $openMenus
            .filter((_, menu) => !$(event.target).closest(menu).length)
            .find('details')
            .removeAttr('open');
    });
});
