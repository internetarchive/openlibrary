// used in templates/covers/add.html
const Carousel = {
    add: function(selector, a, b, c, d, e, f, loadMore) {
        a = a || 6;
        b = b || 5;
        c = c || 4;
        d = d || 3;
        e = e || 2;
        f = f || 1;

        var responsive_settings = [
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

        var availabilityStatuses = {
            'open': {cls: 'cta-btn--available', cta: 'Read'},
            'borrow_available': {cls: 'cta-btn--available', cta: 'Borrow'},
            'borrow_unavailable': {cls: 'cta-btn--unavailable', cta: 'Join Waitlist'},
            'error': {cls: 'cta-btn--missing', cta: 'No eBook'}
        };

        var addWork = function(work) {
            var availability = work.availability.status;
            var cover_id = work.covers? work.covers[0] : work.cover_id;
            var ocaid = work.availability.identifier;
            var cls = availabilityStatuses[availability].cls;
            var url = (cls == 'cta-btn--available') ?
                ('/borrow/ia/' + ocaid) : (cls == 'cta-btn--unavailable') ?
                    ('/books/' + work.availability.openlibrary_edition) : work.key;
            var cta = availabilityStatuses[availability].cta;
            var isClickable = availability == 'error' ? 'disabled' : '';

            return '<div class="book carousel__item slick-slide slick-active" ' +
                '"aria-hidden="false" role="option">' +
                '<div class="book-cover">' +
                  '<a href="' + work.key + '" ' + isClickable + '>' +
                    '<img class="bookcover" width="130" height="200" title="' +
                      work.title + '" ' +
                      'src="//covers.openlibrary.org/b/id/' + cover_id + '-M.jpg">' +
                  '</a>' +
                '</div>' +
                '<div class="book-cta">' +
                  '<a class="btn cta-btn ' + cls + '" href="' + url +
                    '" data-ol-link-track="subjects" ' +
                    'title="' + cta + ': ' + work.title +
                    '" data-key="subjects" data-ocaid="' + ocaid + '">' + cta +
                  '</a>' +
                '</div>' +
              '</div>';
        }

        // if a loadMore config is provided and it has a (required) url
        if (loadMore && loadMore.url) {
            var url;
            try {
                // exception handling needed in case loadMore.url is relative path
                url = new URL(loadMore.url);
            } catch (e) {
                url = new URL(window.location.origin + loadMore.url);
            }
            var default_limit = 18; // 3 pages of 6 books
            url.searchParams.set('limit', loadMore.limit || default_limit);
            loadMore.pageMode = loadMore.pageMode === 'page' ? 'page' : 'offset'; // verify pagination mode
            loadMore.locked = false; // prevent additional calls when not in critical section

            // Bind an action listener to this carousel on resize or advance
            $(selector).on('afterChange', function() {
                var totalSlides = $(selector + '.slick-slider')
                    .slick("getSlick").$slides.length;
                var numActiveSlides = $(selector + ' .slick-active').length;
                var currentLastSlide = $(selector + '.slick-slider')
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
                        'url': url,
                        'type': 'GET',
                        success: function(subject_results) {
                            $.each(subject_results.works, function(work_idx) {
                                var work = subject_results.works[work_idx];
                                var lastSlidePos = $(selector + '.slick-slider')
                                    .slick("getSlick").$slides.length - 1;
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
