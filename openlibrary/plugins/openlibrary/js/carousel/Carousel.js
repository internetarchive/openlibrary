// Slick#1.6.0 is not on npm
import 'slick-carousel';
import '../../../../../static/css/components/carousel--js.less';
import { buildPartialsUrl } from  '../utils.js';

/**
 * @typedef {Object} CarouselConfig
 * @property {[number, number, number, number, number, number]} booksPerBreakpoint
 *      number of books to show at: [default, >1200px, >1024px, >600px, >480px, >360px]
 * @property {String} analyticsCategory
 * @property {String} carouselKey
 * @property {Object} [loadMore] configuration for loading more items
 * @property {String} loadMore.url to use to load more items
 * @property {Number} loadMore.limit of new items to receive
 * @property {'page' | 'offset'} loadMore.pageMode
 * -- INTERNAL --
 * @property {boolean} loadMore.locked PRIVATE used internally to prevent multiple requests
 * @property {boolean} loadMore.allDone PRIVATE used internally to indicate no more items to load
 * @property {number} loadMore.page PRIVATE used internally to track current page OR offset
 * @property {Object} loadMore.extraParams PRIVATE used internally to track extra params
 */

// used in templates/covers/add.html
export class Carousel {
    /**
     * @param {jQuery} $container
     */
    constructor($container) {
        /** @type {CarouselConfig} */
        this.config = Object.assign(
            {
                booksPerBreakpoint: [6, 5, 4, 3, 2, 1],
                analyticsCategory: 'Carousel',
                carouselKey: '',
            },
            JSON.parse($container.attr('data-config'))
        );

        /** @type {CarouselConfig['loadMore']} */
        this.loadMore = Object.assign(
            {
                limit: 18, // 3 pages of 6 books
                pageMode: 'page',
                locked: false,
                allDone: false,
                page: 1,
            },
            this.config.loadMore || {}
        );

        /** @type {jquery} */
        this.$container = $container;

        //This loads in i18n strings from a hidden input element, generated in the books/custom_carousel.html template.
        const i18nInput = document.querySelector('input[name="carousel-i18n-strings"]')
        if (i18nInput) {
            this.i18n = JSON.parse(i18nInput.value);
        }
    }

    get slick() {
        return this.$container.slick('getSlick');
    }

    init() {
        this.$container.slick({
            infinite: false,
            speed: 300,
            slidesToShow: this.config.booksPerBreakpoint[0],
            slidesToScroll: this.config.booksPerBreakpoint[0],
            responsive: [1200, 1024, 600, 480, 360]
                .map((breakpoint, i) => ({
                    breakpoint: breakpoint,
                    settings: {
                        slidesToShow: this.config.booksPerBreakpoint[i + 1],
                        slidesToScroll: this.config.booksPerBreakpoint[i + 1],
                        infinite: false,
                    }
                }))
        });

        // Slick internally changes the click handlers on the next/prev buttons,
        // so we listen via the container instead
        this.$container.on('click', '.slick-next', (ev) => {
            // Note: This will actually fail on the last 'next', but that's okay
            if ($(ev.target).hasClass('slick-disabled')) return;

            window.archive_analytics.ol_send_event_ping({
                category: this.config.analyticsCategory,
                action: 'Next',
                label: this.config.carouselKey,
            });
        });

        this.$container.on('swipe', (ev, _slick, direction) => {
            if (direction === 'left') {
                window.archive_analytics.ol_send_event_ping({
                    category: this.config.analyticsCategory,
                    action: 'Next',
                    label: this.config.carouselKey,
                });
            }
        });

        // if a loadMore config is provided and it has a (required) url
        const loadMore = this.loadMore;
        if (loadMore && loadMore.queryType) {
            // Bind an action listener to this carousel on resize or advance
            this.$container.on('afterChange', (_ev, _slick, curSlide) => {
                window.ILE?.handleNewDom(this.$container[0]);

                const totalSlides = this.slick.$slides.length;
                const numActiveSlides = this.slick.$slides.filter('.slick-active').length;
                // this allows us to pre-load before hitting last page
                const needsMoreCards = totalSlides - curSlide <= (numActiveSlides * 2);

                if (!loadMore.locked && !loadMore.allDone && needsMoreCards) {
                    loadMore.locked = true; // lock for critical section

                    if (loadMore.pageMode === 'page') {
                        loadMore.page++;
                    } else { // i.e. offset, start from last slide
                        loadMore.page = totalSlides;
                    }

                    this.fetchPartials();
                }
            });

            document.addEventListener('filter', (ev) => {
                loadMore.extraParams = {published_in: `${ev.detail.yearFrom}-${ev.detail.yearTo}`};

                // Reset the page count - the result set is now 'new'
                if (loadMore.pageMode === 'page') {
                    loadMore.page = 1;
                } else {
                    loadMore.page = 0;
                }
                loadMore.allDone = false;

                this.clearCarousel();
                this.fetchPartials();
            });
        }
    }

    fetchPartials() {
        const loadMore = this.loadMore
        const url = buildPartialsUrl('CarouselLoadMore', {
            queryType: loadMore.queryType,
            q: loadMore.q,
            limit: loadMore.limit,
            page: loadMore.page,
            sorts: loadMore.sorts,
            subject: loadMore.subject,
            pageMode: loadMore.pageMode,
            hasFulltextOnly: loadMore.hasFulltextOnly,
            secondaryAction: loadMore.secondaryAction,
            key: loadMore.key,
            ...loadMore.extraParams
        });
        this.appendLoadingSlide();
        $.ajax({url: url, type: 'GET'})
            .then((results) => {
                this.removeLoadingSlide();
                const cards = results.partials || []
                cards.forEach(card => this.slick.addSlide(card))

                if (!cards.length) {
                    loadMore.allDone = true;
                }
                loadMore.locked = false;
            })
    }

    clearCarousel() {
        this.slick.removeSlide(this.slick.$slides.length, true, true);
    }

    appendLoadingSlide() {
        this.slick.addSlide(`<div class="carousel__item carousel__loading-end">${this.i18n['loading']}</div>`);
    }

    removeLoadingSlide() {
        this.slick.removeSlide(this.slick.$slides.length - 1);
    }
}
