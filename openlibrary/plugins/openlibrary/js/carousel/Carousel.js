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
        var responsive_settings, availabilityStatuses, addWork, default_limit;

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
            error: {cls: 'cta-btn--missing', cta: 'Not In Library'},
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
            const url = cls == 'cta-btn--available' ? `/borrow/ia/${ocaid}` : work.key;

            if (!cover.id && ocaid) {
                cover.type = 'ia';
                cover.id = ocaid;
            }

            const $el = $(`
                <div class="book carousel__item">
                    <div class="book-cover">
                        <a href="${work.key}">
                            <img class="bookcover" src="//covers.openlibrary.org/b/${cover.type}/${cover.id}-M.jpg">
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
        if (loadMore && loadMore.url) {
            // handle relative path
            const url = loadMore.url.startsWith('/') ? new URL(location.origin + loadMore.url) : new URL(loadMore.url);

            default_limit = 18; // 3 pages of 6 books
            url.searchParams.set('limit', loadMore.limit || default_limit);
            loadMore.pageMode = loadMore.pageMode === 'page' ? 'page' : 'offset'; // verify pagination mode
            loadMore.locked = false; // prevent additional calls when not in critical section

            // Bind an action listener to this carousel on resize or advance
            $(selector).on('afterChange', function(ev, slick, curSlide) {
                const totalSlides = slick.$slides.length;
                const numActiveSlides = slick.$slides.filter('.slick-active').length;
                // this allows us to pre-load before hitting last page
                const isOn2ndLastPage = curSlide >= Math.max(0, totalSlides - numActiveSlides * 2);

                if (!loadMore.locked && !loadMore.allDone && isOn2ndLastPage) {
                    loadMore.locked = true; // lock for critical section
                    slick.addSlide('<div class="carousel__item carousel__loading-end">Loading...</div>');

                    if (loadMore.pageMode == 'page') {
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
        }
    }
};

export default Carousel;
