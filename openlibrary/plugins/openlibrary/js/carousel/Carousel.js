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
 * @property {String} loadMore.pageMode of page e.g. `offset`
 */

// used in templates/covers/add.html
export class Carousel {
    /**
     * @param {jQuery} $container
     */
    constructor($container) {
        var availabilityStatuses, addWork, default_limit;

        /** @type {CarouselConfig} */
        const config = JSON.parse($container.attr('data-config'));

        $container.slick({
            infinite: false,
            speed: 300,
            slidesToShow: config.booksPerBreakpoint[0],
            slidesToScroll: config.booksPerBreakpoint[0],
            responsive: [1200, 1024, 600, 480, 360]
                .map((breakpoint, i) => ({
                    breakpoint: breakpoint,
                    settings: {
                        slidesToShow: config.booksPerBreakpoint[i + 1],
                        slidesToScroll: config.booksPerBreakpoint[i + 1],
                        infinite: false,
                    }
                }))
        });
        //This loads in i18n strings from a hidden input element, generated in the books/custom_carousel.html template.
        const i18nValues = JSON.parse($('input[name="carousel-i18n-strings"]').attr('value'))
        availabilityStatuses = {
            open: {cls: 'cta-btn--available', cta: i18nValues['open']},
            borrow_available: {cls: 'cta-btn--available', cta: i18nValues['borrow_available']},
            borrow_unavailable: {cls: 'cta-btn--unavailable', cta: i18nValues['borrow_unavailable']},
            error: {cls: 'cta-btn--missing', cta: i18nValues['error']},
            // private: {cls: 'cta-btn--available', cta: 'Preview'}
        };

        addWork = function(work) {
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
            const availabilityStatus = availabilityStatuses[availability.status] || availabilityStatuses.error;
            const cls = availabilityStatus.cls;
            const cta = availabilityStatus.cta;
            const url = cls === 'cta-btn--available' ? `/borrow/ia/${ocaid}` : work.key;

            if (!cover.id && ocaid) {
                cover.type = 'ia';
                cover.id = ocaid;
            }

            let bookCover;
            if (cover.id) {
                bookCover = `<img class="bookcover" src="//covers.openlibrary.org/b/${cover.type}/${cover.id}-M.jpg?default='https://openlibrary.org/images/icons/avatar_book.png'">`
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

        // if a loadMore config is provided and it has a (required) url
        const loadMore = config.loadMore;
        if (loadMore && loadMore.url) {
            // handle relative path
            const url = loadMore.url.startsWith('/') ? new URL(location.origin + loadMore.url) : new URL(loadMore.url);

            default_limit = 18; // 3 pages of 6 books
            url.searchParams.set('limit', loadMore.limit || default_limit);
            loadMore.pageMode = loadMore.pageMode === 'page' ? 'page' : 'offset'; // verify pagination mode
            loadMore.locked = false; // prevent additional calls when not in critical section

            // Bind an action listener to this carousel on resize or advance
            $container.on('afterChange', function(ev, slick, curSlide) {
                const totalSlides = slick.$slides.length;
                const numActiveSlides = slick.$slides.filter('.slick-active').length;
                // this allows us to pre-load before hitting last page
                const isOn2ndLastPage = curSlide >= Math.max(0, totalSlides - numActiveSlides * 2);

                if (!loadMore.locked && !loadMore.allDone && isOn2ndLastPage) {
                    loadMore.locked = true; // lock for critical section
                    slick.addSlide(`<div class="carousel__item carousel__loading-end">${i18nValues['loading']}</div>`);
                    if (loadMore.pageMode === 'page') {
                        // for first time, we're on page 1 already so initialize as page 2
                        // otherwise advance to next page
                        loadMore.page = loadMore.page ? loadMore.page + 1 : 2;
                    } else { // i.e. offset, start from last slide
                        loadMore.page = totalSlides;
                    }

                    // update the current page or offset within the URL
                    url.searchParams.set(loadMore.pageMode, loadMore.page);

                    $.ajax({ url: url, type: 'GET' })
                        .then(function(results) {
                            const works = results.works || results.docs;
                            // Remove loading indicator
                            slick.removeSlide(totalSlides);
                            works.forEach(work => slick.addSlide(addWork(work)));
                            if (!works.length) {
                                loadMore.allDone = true;
                            }
                            loadMore.locked = false;
                        });
                }
            });

            document.addEventListener('filter', function(ev) {
                url.searchParams.set('published_in', `${ev.detail.yearFrom}-${ev.detail.yearTo}`);

                // Reset the page count - the result set is now 'new'
                loadMore.page = 2;

                const slick = $container.slick('getSlick');
                const totalSlides = slick.$slides.length;

                // Remove the current slides
                slick.removeSlide(totalSlides, true, true);
                slick.addSlide(`<div class="carousel__item carousel__loading-end">${i18nValues['loading']}</div>`);

                $.ajax({ url: url, type: 'GET' })
                    .then(function(results) {
                        const works = results.works || results.docs;
                        // Remove loading indicator
                        slick.slickRemove(0);
                        works.forEach(work => slick.addSlide(addWork(work)));
                        if (!works.length) {
                            loadMore.allDone = true;
                        }
                        loadMore.locked = false;
                    });
            });
        }
    }
}
