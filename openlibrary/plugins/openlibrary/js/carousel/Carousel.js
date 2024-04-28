// Slick#1.6.0 is not on npm
import 'slick-carousel';
import '../../../../../static/css/components/carousel--js.less';

/**
 * @typedef {Object} CarouselConfig
 * @property {[number, number, number, number, number, number]} booksPerBreakpoint
 *      number of books to show at: [default, >1200px, >1024px, >600px, >480px, >360px]
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
        this.config = JSON.parse($container.attr('data-config'));

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

            this.availabilityStatuses = {
                open: {cls: 'cta-btn--available', cta: this.i18n['open']},
                borrow_available: {cls: 'cta-btn--available', cta: this.i18n['borrow_available']},
                borrow_unavailable: {cls: 'cta-btn--unavailable', cta: this.i18n['borrow_unavailable']},
                error: {cls: 'cta-btn--missing', cta: this.i18n['error']},
                // private: {cls: 'cta-btn--available', cta: 'Preview'}
            };
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

        // if a loadMore config is provided and it has a (required) url
        const loadMore = this.loadMore;
        if (loadMore && loadMore.url) {
            // Bind an action listener to this carousel on resize or advance
            this.$container.on('afterChange', (_ev, _slick, curSlide) => {
                const totalSlides = this.slick.$slides.length;
                const numActiveSlides = this.slick.$slides.filter('.slick-active').length;
                // this allows us to pre-load before hitting last page
                const isOn2ndLastPage = curSlide >= Math.max(0, totalSlides - numActiveSlides * 2);

                if (!loadMore.locked && !loadMore.allDone && isOn2ndLastPage) {
                    loadMore.locked = true; // lock for critical section

                    if (loadMore.pageMode === 'page') {
                        loadMore.page++;
                    } else { // i.e. offset, start from last slide
                        loadMore.page = totalSlides;
                    }

                    this.fetchMore();
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
                this.fetchMore();
            });
        }
    }

    renderWork(work) {
        const availability = work.availability || {};
        const ocaid = availability.identifier ||
            work.lending_identifier_s ||
            (work.ia ? work.ia[0] : undefined);
        // Use solr data to augment availability API
        if (!availability.status || availability.status === 'error') {
            if (work.lending_identifier_s) {
                availability.status = 'borrow_available';
            } else if (ocaid) {
                availability.status = 'private';
            }
        }
        const cover = {
            type: 'id',
            id: work.covers ? work.covers[0] : (work.cover_id || work.cover_i)
        };
        const availabilityStatus = this.availabilityStatuses[availability.status] || this.availabilityStatuses.error;
        const cls = availabilityStatus.cls;
        const cta = availabilityStatus.cta;
        const url = cls === 'cta-btn--available' ? `/borrow/ia/${ocaid}` : work.key;

        if (!cover.id && ocaid) {
            cover.type = 'ia';
            cover.id = ocaid;
        }

        let bookCover;
        if (cover.id) {
            bookCover = `
                <img
                    class="bookcover"
                    src="//covers.openlibrary.org/b/${cover.type}/${cover.id}-M.jpg?default=https://openlibrary.org/images/icons/avatar_book.png"
                >`
        } else {
            bookCover = `
                <div class="carousel__item__blankcover bookcover">
                    <div class="carousel__item__blankcover--title">${work.title}</div>
                    ${work.author_name ? `<div class="carousel__item__blankcover--authors">${work.author_name}</div>` : ''}
                </div>`
        }

        const $el = $(`
            <div class="book carousel__item">
                <div class="book-cover">
                    <a href="${work.key}">
                        ${bookCover}
                    </a>
                </div>
                <div class="book-cta">
                    <a class="btn cta-btn ${cls}"
                       data-ol-link-track="subjects"
                       data-key="subjects"
                   >${cta}</a>
                </div>
            </div>`);
        $el.find('.bookcover').attr('title', work.title);
        $el.find('.cta-btn')
            .attr('title', `${cta}: ${work.title}`)
            .attr('data-ocaid', ocaid)
            .attr('href', url);
        return $el;
    }

    fetchMore() {
        const loadMore = this.loadMore;
        // update the current page or offset within the URL
        const url = loadMore.url.startsWith('/') ? new URL(location.origin + loadMore.url) : new URL(loadMore.url);
        url.searchParams.set('limit', loadMore.limit);
        url.searchParams.set(loadMore.pageMode, loadMore.page);
        //set extraParams
        for (const key in loadMore.extraParams) {
            url.searchParams.set(key, loadMore.extraParams[key]);
        }


        this.appendLoadingSlide();
        $.ajax({ url: url, type: 'GET' })
            .then((results) => {
                this.removeLoadingSlide();
                const works = results.works || results.docs;
                works.forEach(work => this.slick.addSlide(this.renderWork(work)));
                if (!works.length) {
                    loadMore.allDone = true;
                }
                loadMore.locked = false;
            });
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
