import 'jquery';
import { exposeGlobally } from './jsdef';
import initAnalytics from './ol.analytics';
import init from './ol.js';
import initServiceWorker from './service-worker-init.js'
import '../../../../static/css/js-all.less';
// polyfill Promise support for IE11
import Promise from 'promise-polyfill';

// Eventually we will export all these to a single global ol, but in the mean time
// we add them to the window object for backwards compatibility.
exposeGlobally();

window.jQuery = jQuery;
window.$ = jQuery;

window.Promise = Promise;

// Init the service worker first since it does caching
initServiceWorker();

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

    // Polyfill for .matches()
    if (!Element.prototype.matches) {
        Element.prototype.matches =
          Element.prototype.msMatchesSelector ||
          Element.prototype.webkitMatchesSelector;
    }

    // Polyfill for .closest()
    if (!Element.prototype.closest) {
        Element.prototype.closest = function(s) {
            let el = this;
            do {
                if (Element.prototype.matches.call(el, s)) return el;
                el = el.parentElement || el.parentNode;
            } while (el !== null && el.nodeType === 1);
            return null;
        };
    }

    const $tabs = $('.ol-tabs');
    if ($tabs.length) {
        import(/* webpackChunkName: "tabs" */ './tabs')
            .then((module) => module.initTabs($tabs));
    }

    const $validates = $('form.validate');
    if ($validates.length) {
        import(/* webpackChunkName: "validate" */ './validate')
            .then((module) => module.init($));
    }

    const $autocomplete = $('.multi-input-autocomplete');
    if ($autocomplete.length) {
        import(/* webpackChunkName: "autocomplete" */ './autocomplete')
            .then((module) => module.init($));
    }

    // hide all images in .no-img
    $('.no-img img').hide();

    // disable save button after click
    $('button[name=\'_save\']').on('submit', function() {
        $(this).attr('disabled', true);
    });

    // wmd editor
    const $markdownTextAreas = $('textarea.markdown');
    if ($markdownTextAreas.length) {
        import(/* webpackChunkName: "markdown-editor" */ './markdown-editor')
            .then((module) => module.initMarkdownEditor($markdownTextAreas));
    }

    init($);

    // conditionally load functionality based on what's in the page
    if (document.getElementsByClassName('editions-table--progressively-enhanced').length) {
        import(/* webpackChunkName: "editions-table" */ './editions-table')
            .then(module => module.initEditionsTable());
    }

    const edition = document.getElementById('addWork');
    const autocompleteAuthor = document.querySelector('.multi-input-autocomplete--author');
    const autocompleteLanguage = document.querySelector('.multi-input-autocomplete--language');
    const autocompleteWorks = document.querySelector('.multi-input-autocomplete--works');
    const autocompleteSeeds = document.querySelector('.multi-input-autocomplete--seeds');
    const autocompleteSubjects = document.querySelector('.csv-autocomplete--subjects');
    const addRowButton = document.getElementById('add_row_button');
    const roles = document.querySelector('#roles');
    const classifications = document.querySelector('#classifications');
    const excerpts = document.getElementById('excerpts');
    const links = document.getElementById('links');

    // conditionally load for user edit page
    if (
        edition ||
        autocompleteAuthor || autocompleteLanguage || autocompleteWorks ||
        autocompleteSeeds || autocompleteSubjects ||
        addRowButton || roles || classifications ||
        excerpts || links
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
                if (classifications) {
                    module.initClassificationValidation();
                }
                if (autocompleteLanguage) {
                    module.initLanguageMultiInputAutocomplete();
                }
                if (autocompleteWorks) {
                    module.initWorksMultiInputAutocomplete();
                }
                if (autocompleteSubjects) {
                    module.initSubjectsAutocomplete();
                }
                if (autocompleteSeeds) {
                    module.initSeedsMultiInputAutocomplete();
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

    // conditionally load for type changing input
    const typeChanger = document.getElementById('type.key')
    if (typeChanger) {
        import(/* webpackChunkName: "type-changer" */ './type_changer.js')
            .then(module => module.initTypeChanger(typeChanger));
    }

    // conditionally load validation and submission js for registration form
    if (document.querySelector('form[name=signup]')) {
        import(/* webpackChunkName: "signup" */'./signup.js')
            .then(module => module.initSignupForm());
    }

    // conditionally load submission js for login form
    if (document.querySelector('form[name=login]')) {
        import(/* webpackChunkName: "signup" */'./signup.js')
            .then(module => module.initLoginForm());
    }

    // conditionally load clamping components
    const readMoreComponents = document.getElementsByClassName('read-more');
    const clampers = document.querySelectorAll('.clamp');
    if (readMoreComponents.length || clampers.length) {
        import(/* webpackChunkName: "readmore" */ './readmore.js')
            .then(module => {
                if (readMoreComponents.length) {
                    module.ReadMoreComponent.init();
                }
                if (clampers.length) {
                    module.initClampers(clampers);
                }
            });
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
    // conditionally load list seed item deletion dialog functionality based on id on lists pages
    if (document.getElementById('listResults')) {
        import(/* webpackChunkName: "ListViewBody" */'./lists/ListViewBody.js');
    }

    // Enable any carousels in the page
    const $carouselElements = $('.carousel--progressively-enhanced');
    if ($carouselElements.length) {
        import(/* webpackChunkName: "carousel" */ './carousel/Carousel.js')
            .then((module) => {
                $carouselElements.each((_i, el) => new module.Carousel($(el)).init());
                $('.slick-slide').each(function () {
                    if ($(this).attr('aria-describedby') !== undefined) {
                        $(this).attr('id',$(this).attr('aria-describedby'));
                    }
                });
            })
    }
    if ($('script[type="text/json+graph"]').length > 0) {
        import(/* webpackChunkName: "graphs" */ './graphs')
            .then((module) => module.init());
    }

    const readingLogCharts = document.querySelector('.readinglog-charts')
    if (readingLogCharts) {
        const readingLogConfig = JSON.parse(readingLogCharts.dataset.config)
        import(/* webpackChunkName: "readinglog-stats" */ './readinglog_stats')
            .then(module => module.init(readingLogConfig));
    }

    if (document.getElementsByClassName('toast').length) {
        import(/* webpackChunkName: "Toast" */ './Toast')
            .then((module) => {
                Array.from(document.getElementsByClassName('toast'))
                    .forEach(el => new module.Toast($(el)));
            });
    }

    if ($('.lazy-thing-preview').length) {
        import(/* webpackChunkName: "lazy-thing-preview" */ './lazy-thing-preview')
            .then((module) => new module.LazyThingPreview().init());
    }

    const $observationModalLinks = $('.observations-modal-link');
    const $notesModalLinks = $('.notes-modal-link');
    const $notesPageButtons = $('.note-page-buttons');
    const $shareModalLinks = $('.share-modal-link');
    if ($observationModalLinks.length || $notesModalLinks.length || $notesPageButtons.length || $shareModalLinks.length) {
        import(/* webpackChunkName: "modal-links" */ './modals')
            .then(module => {
                if ($observationModalLinks.length) {
                    module.initObservationsModal($observationModalLinks);
                }
                if ($notesModalLinks.length) {
                    module.initNotesModal($notesModalLinks);
                }
                if ($notesPageButtons.length) {
                    module.addNotesPageButtonListeners();
                }
                if ($shareModalLinks.length) {
                    module.initShareModal($shareModalLinks)
                }
            });
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

    if (document.getElementById('autofill-dev-credentials')) {
        document.getElementById('username').value = 'openlibrary@example.com'
        document.getElementById('password').value = 'admin123'
        document.getElementById('remember').checked = true
    }
    const anonymizationButton = document.querySelector('.account-anonymization-button')
    const adminLinks = document.getElementById('adminLinks')
    const confirmButtons = document.querySelectorAll('.do-confirm')
    if (adminLinks || anonymizationButton || confirmButtons.length) {
        import(/* webpackChunkName: "admin" */ './admin')
            .then(module => {
                if (adminLinks) {
                    module.initAdmin();
                }
                if (anonymizationButton) {
                    module.initAnonymizationButton(anonymizationButton);
                }
                if (confirmButtons.length) {
                    module.initConfirmationButtons(confirmButtons);
                }
            });
    }

    if (window.matchMedia('(display-mode: standalone)').matches) {
        import(/* webpackChunkName: "offline-banner" */ './offline-banner')
            .then((module) => module.initOfflineBanner());
    }

    const searchFacets = document.getElementById('searchFacets')
    if (searchFacets) {
        import(/* webpackChunkName: "search" */ './search')
            .then((module) => module.initSearchFacets(searchFacets));
    }

    // Conditionally load Integrated Librarian Environment
    if (document.getElementsByClassName('show-librarian-tools').length) {
        import(/* webpackChunkName: "ile" */ './ile')
            .then((module) => module.init());
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

    const droppers = document.querySelectorAll('.dropper')
    const genericDroppers = document.querySelectorAll('.generic-dropper-wrapper')
    if (droppers.length || genericDroppers.length) {
        import(/* webpackChunkName: "droppers" */ './dropper')
            .then((module) => {
                module.initDroppers(droppers)
                module.initGenericDroppers(genericDroppers)
            })
    }

    // My Books Droppers:
    const myBooksDroppers = document.querySelectorAll('.my-books-dropper')
    if (myBooksDroppers.length) {
        const actionableListShowcases = document.querySelectorAll('.actionable-item')

        import(/* webpackChunkName: "my-books" */ './my-books')
            .then((module) => {
                module.initMyBooksAffordances(myBooksDroppers, actionableListShowcases)
            })
    }

    // TODO: Make these selectors a consistent interface
    const $dialogs = $('.dialog--open,.dialog--close,#noMaster,#confirmMerge,#leave-waitinglist-dialog,.cta-btn--preview');
    if ($dialogs.length) {
        import(/* webpackChunkName: "dialog" */ './dialog')
            .then(module => module.initDialogs())
    }

    const nativeDialogs = document.querySelectorAll('.native-dialog');
    if (nativeDialogs.length) {
        import(/* webpackChunkName: "native-dialog" */ './native-dialog')
            .then(module => module.initDialogs(nativeDialogs))
    }

    const setGoalLinks = document.querySelectorAll('.set-reading-goal-link')
    const goalEditLinks = document.querySelectorAll('.edit-reading-goal-link')
    const goalSubmitButtons = document.querySelectorAll('.reading-goal-submit-button')
    const checkInForms = document.querySelectorAll('.check-in')
    const checkInPrompts = document.querySelectorAll('.check-in-prompt')
    const checkInEditLinks = document.querySelectorAll('.prompt-edit-date')
    const yearElements = document.querySelectorAll('.use-local-year')
    if (setGoalLinks.length || goalEditLinks.length || goalSubmitButtons.length || checkInForms.length || checkInPrompts.length || checkInEditLinks.length || yearElements.length) {
        import(/* webpackChunkName: "check-ins" */ './check-ins')
            .then((module) => {
                if (setGoalLinks.length) {
                    module.initYearlyGoalPrompt(setGoalLinks)
                }
                if (goalEditLinks.length) {
                    module.initGoalEditLinks(goalEditLinks)
                }
                if (goalSubmitButtons.length) {
                    module.initGoalSubmitButtons(goalSubmitButtons)
                }
                if (checkInForms.length) {
                    module.initCheckInForms(checkInForms)
                }
                if (checkInPrompts.length) {
                    module.initCheckInPrompts(checkInPrompts)
                }
                if (checkInEditLinks.length) {
                    module.initCheckInEdits(checkInEditLinks)
                }
                if (yearElements.length) {
                    module.displayLocalYear(yearElements)
                }
            })
    }

    $(document).on('click', '.slide-toggle', function () {
        $(`#${$(this).attr('aria-controls')}`).slideToggle();
    });

    $('#wikiselect').on('focus', function(){$(this).trigger('select');})

    $('.hamburger-component .mask-menu').on('click', function () {
        $('details[open]').not(this).removeAttr('open');
    });

    $('.header-dropdown').on('keydown', function (event) {
        if (event.key === 'Escape') {
            $('.header-dropdown > details[open]').removeAttr('open');
        }
    });

    $('.dropdown-menu').each(function() {
        $(this).find('a').last().on('focusout', function() {
            $('.header-dropdown > details[open]').removeAttr('open');
        });
    });

    // Open one dropdown at a time.
    $(document).on('click', function (event) {
        const $openMenus = $('.header-dropdown details[open]').parents('.header-dropdown');
        $openMenus
            .filter((_, menu) => !$(event.target).closest(menu).length)
            .find('details')
            .removeAttr('open');
    });

    // Prevent default star rating behavior:
    const ratingForms = document.querySelectorAll('.star-rating-form')
    if (ratingForms.length) {
        import(/* webpackChunkName: "star-ratings" */'./star-ratings')
            .then((module) => module.initRatingHandlers(ratingForms));
    }

    // Book page navbar initialization:
    const navbarWrappers = document.querySelectorAll('.nav-bar-wrapper')
    if (navbarWrappers.length) {
        // Add JS for book page navbar:
        import(/* webpackChunkName: "nav-bar" */ './edition-nav-bar')
            .then((module) => {
                module.initNavbars(navbarWrappers)
            });
        // Add sticky title component animations to desktop views:
        import(/* webpackChunkName: "compact-title" */ './compact-title')
            .then((module) => {
                const compactTitle = document.querySelector('.compact-title')
                const desktopNavbar = [...navbarWrappers].find(elem => elem.classList.contains('desktop-only'))
                module.initCompactTitle(desktopNavbar, compactTitle)
            })
    }

    // Add functionality for librarian merge request table:
    const librarianQueue = document.querySelector('.librarian-queue-wrapper')

    if (librarianQueue) {
        import(/* webpackChunkName: "merge-request-table" */'./merge-request-table')
            .then(module => {
                if (librarianQueue) {
                    module.initLibrarianQueue(librarianQueue)
                }
            })
    }

    // Add functionality to the team page for filtering members:
    const teamCards = document.querySelector('.teamCards_container')
    if (teamCards) {
        import('./team')
            .then(module => {
                if (teamCards) {
                    module.initTeamFilter();
                }
            })
    }

    // Add new providers in edit edition view:
    const addProviderRowLink = document.querySelector('#add-new-provider-row')
    if (addProviderRowLink) {
        import(/* webpackChunkName "add-provider-link" */ './add_provider')
            .then(module => module.initAddProviderRowLink(addProviderRowLink))
    }


    // Allow banner announcements to be dismissed by logged-in users:
    const banners = document.querySelectorAll('.page-banner--dismissable')
    if (banners.length) {
        import(/* webpackChunkName: "dismissible-banner" */ './banner')
            .then(module => module.initDismissibleBanners(banners))
    }

    const returnForms = document.querySelectorAll('.return-form')
    if (returnForms.length) {
        import(/* webpackChunkName: "return-form" */ './return-form')
            .then(module => module.initReturnForms(returnForms))
    }

    const crumbs = document.querySelectorAll('.crumb select');
    if (crumbs.length) {
        import(/* webpackChunkName: "breadcrumb-select" */ './breadcrumb_select')
            .then(module => module.initBreadcrumbSelect(crumbs));
    }

    const leaveWaitlistLinks = document.querySelectorAll('a.leave');
    if (leaveWaitlistLinks.length && document.getElementById('leave-waitinglist-dialog')) {
        import(/* webpackChunkName: "waitlist" */ './waitlist')
            .then(module => module.initLeaveWaitlist(leaveWaitlistLinks));
    }

    const thirdPartyLoginsIframe = document.getElementById('ia-third-party-logins');
    if (thirdPartyLoginsIframe) {
        import(/* webpackChunkName: "ia_thirdparty_logins" */ './ia_thirdparty_logins')
            .then((module) => module.initMessageEventListener(thirdPartyLoginsIframe));
    }

    // Password visibility toggle:
    const passwordVisibilityToggle = document.querySelector('.password-visibility-toggle')
    if (passwordVisibilityToggle) {
        import(/* webpackChunkName: "password-visibility-toggle" */ './password-toggle')
            .then(module => module.initPasswordToggling(passwordVisibilityToggle))
    }

    // Affiliate links:
    const affiliateLinksSection = document.querySelectorAll('.affiliate-links-section')
    if (affiliateLinksSection.length) {
        import(/* webpackChunkName: "affiliate-links" */ './affiliate-links')
            .then(module => module.initAffiliateLinks(affiliateLinksSection))
    }

    // Fulltext search box:
    const  fulltextSearchSuggestion = document.querySelector('#fulltext-search-suggestion')
    if (fulltextSearchSuggestion) {
        import(/* webpackChunkName: "fulltext-search-suggestion" */ './fulltext-search-suggestion')
            .then(module => module.initFulltextSearchSuggestion(fulltextSearchSuggestion))
    }

    // Go back redirect:
    const backLinks = document.querySelectorAll('.go-back-link')
    if (backLinks.length) {
        import (/* webpackChunkName: "go-back-links" */ './go-back-links')
            .then(module => module.initGoBackLinks(backLinks))
    }
});

