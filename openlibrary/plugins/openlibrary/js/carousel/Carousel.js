// used in templates/covers/add.html
const Carousel = {
    /**
     * @param {String} selector (CSS) referring to the node to be enhanced
     * @param {Number} [a] number of books to show (default)
     * @param {Number} [b] number of books to show @1200px or more
     * @param {Number} [c] number of books to show @1024px or more
     * @param {Number} [d] number of books to show @600px or more
     * @param {Number} [e] number of books to show @480px or more
     * @param {Number} [f] number of books to show @360px or more
     * @param {Object} [loadMore] configuration
     * @param {String} loadMore.url to use to load more items
     * @param {Number} loadMore.limit of new items to receive
     * @param {String} loadMore.pageMode of page e.g. `offset`
     */
    add: function(selector, a, b, c, d, e, f, loadMore) {
        var responsive_settings, availabilityStatuses, addWork, url, default_limit;

        a = a || 6;
        b = b || 5;
        c = c || 4;
        d = d || 3;
        e = e || 2;
        f = f || 1;

        responsive_settings = [
            {
                breakpoint: 1200,
                settings: {
                    slidesToShow: b,
                    slidesToScroll: b,
                    infinite: false,
                }
            },
            {
                breakpoint: 1024,
                settings: {
                    slidesToShow: c,
                    slidesToScroll: c,
                    infinite: false,
                }
            },
            {
                breakpoint: 600,
                settings: {
                    slidesToShow: d,
                    slidesToScroll: d
                }
            },
            {
                breakpoint: 480,
                settings: {
                    slidesToShow: e,
                    slidesToScroll: e
                }
            }
        ];
        if (f) {
            responsive_settings.push({
                breakpoint: 360,
                settings: {
                    slidesToShow: f,
                    slidesToScroll: f
                }
            });
        }

        $(selector).slick({
            infinite: false,
            speed: 300,
            slidesToShow: a,
            slidesToScroll: a,
            responsive: responsive_settings
        });

        availabilityStatuses = {
            open: {cls: 'cta-btn--available', cta: 'Read'},
            borrow_available: {cls: 'cta-btn--available', cta: 'Borrow'},
            borrow_unavailable: {cls: 'cta-btn--unavailable', cta: 'Join Waitlist'},
            error: {cls: 'cta-btn--missing', cta: 'No eBook'}
        };

        addWork = function(work) {
            var availability = work.availability.status;
            var ocaid = work.availability.identifier;
            var cover = {
                type: 'id',
                id: work.covers? work.covers[0] : work.cover_id || work.cover_i
            };
            var cls = availabilityStatuses[availability].cls;
            var url = (cls == 'cta-btn--available') ?
                (`/borrow/ia/${ocaid}`) : (cls == 'cta-btn--unavailable') ?
                    (`/books/${work.availability.openlibrary_edition}`) : work.key;
            var cta = availabilityStatuses[availability].cta;
            var isClickable = availability == 'error' ? 'disabled' : '';

            if (!cover.id && ocaid) {
                cover.type = 'ia';
                cover.id = ocaid;
            }

            return `${'<div class="book carousel__item slick-slide slick-active" ' +
                '"aria-hidden="false" role="option">' +
                '<div class="book-cover">' +
                  '<a href="'}${work.key}" ${isClickable}>` +
                    `<img class="bookcover" width="130" height="200" title="${
                        work.title}" ` +
                      `src="//covers.openlibrary.org/b/${cover.type}/${cover.id}-M.jpg">` +
                  '</a>' +
                '</div>' +
                '<div class="book-cta">' +
                  `<a class="btn cta-btn ${cls}" href="${url
                  }" data-ol-link-track="subjects" ` +
                    `title="${cta}: ${work.title
                    }" data-key="subjects" data-ocaid="${ocaid}">${cta
                    }</a>` +
                '</div>' +
              '</div>';
        }

        // if a loadMore config is provided and it has a (required) url
        if (loadMore && loadMore.url) {
            url;
            try {
                // exception handling needed in case loadMore.url is relative path
                url = new URL(loadMore.url);
            } catch (e) {
                url = new URL(window.location.origin + loadMore.url);
            }
            default_limit = 18; // 3 pages of 6 books
            url.searchParams.set('limit', loadMore.limit || default_limit);
            loadMore.pageMode = loadMore.pageMode === 'page' ? 'page' : 'offset'; // verify pagination mode
            loadMore.locked = false; // prevent additional calls when not in critical section

            // Bind an action listener to this carousel on resize or advance
            $(selector).on('afterChange', function() {
                var totalSlides = $(`${selector}.slick-slider`)
                    .slick('getSlick').$slides.length;
                var numActiveSlides = $(`${selector} .slick-active`).length;
                var currentLastSlide = $(`${selector}.slick-slider`)
                    .slick('slickCurrentSlide') + numActiveSlides;
                // this allows us to pre-load before hitting last page
                var lastSlideOn2ndLastPage = (totalSlides - numActiveSlides);

                if (!loadMore.locked && (currentLastSlide >= lastSlideOn2ndLastPage)) {
                    loadMore.locked = true; // lock for critical section
                    document.body.style.cursor='wait'; // change mouse to spin

                    if (loadMore.pageMode == 'page') {
                        // for first time, we're on page 1 already so initialize as page 2
                        // otherwise advance to next page
                        loadMore.page = loadMore.page ? loadMore.page + 1 : 2;
                    } else { // i.e. offset, start from last slide
                        loadMore.page = totalSlides;
                    }

                    // update the current page or offset within the URL
                    url.searchParams.set(loadMore.pageMode, loadMore.page);

                    $.ajax({
                        url: url,
                        type: 'GET',
                        success: function(subject_results) {
                            var works = subject_results.works;
                            if (!works) {
                                works = subject_results.docs;
                            }
                            $.each(works, function(work_idx) {
                                var work = works[work_idx];
                                var lastSlidePos = $(`${selector}.slick-slider`)
                                    .slick('getSlick').$slides.length - 1;
                                $(selector).slick('slickAdd', addWork(work), lastSlidePos);
                            });
                            document.body.style.cursor='default'; // return cursor to ready
                            loadMore.locked = false;
                        }
                    });
                }
            });
        }
    }
};

export default Carousel;
