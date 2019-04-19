// used in templates/covers/add.html
const Carousel = {
    add: function(selector, a, b, c, d, e, f, key, loadMoreUrl) {
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
            // You can unslick at a given breakpoint now by adding:
            // settings: "unslick"
            // instead of a settings object
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
                    '<img class="bookcover" width="130" height="200" title="' + work.title + '" ' +
                         'src="//covers.openlibrary.org/b/id/' + work.cover_id + '-M.jpg">' +
                  '</a>' +
                '</div>' +
                '<div class="book-cta">' +
                  '<a class="btn cta-btn ' + cls + '" href="' + url + '" data-ol-link-track="subjects" ' +
                  'title="' + cta + ': ' + work.title + '" data-key="subjects" data-ocaid="' + ocaid + '">' + cta + '</a>' +
                '</div>' +
              '</div>';
        }

        $('.carousel-'+key).on('afterChange', function() {
            var totalSlides = $('.carousel-' + key + '.slick-slider').slick("getSlick").$slides.length;
            var numActiveSlides = $('.carousel-' + key + ' .slick-active').length;
            var currentLastSlide = $('.carousel-' + key + '.slick-slider').slick('slickCurrentSlide') + numActiveSlides;
            // this allows us to pre-load before hitting last page
            var lastSlideOnSecondToLastPage = (totalSlides - numActiveSlides);

            if (loadMoreUrl && (currentLastSlide >= lastSlideOnSecondToLastPage)) {
                var limit = numActiveSlides * 3;
                var url = loadMoreUrl + '?offset=' + totalSlides + '&limit=' + limit;
                $.ajax({
                    'url': url,
                    'type': 'GET',
                    success: function(subject_results) {
                        $.each(subject_results.works, function(work_idx) {
                            var work = subject_results.works[work_idx];
                            var lastSlidePos = $('.carousel-' + key + '.slick-slider').slick("getSlick").$slides.length - 1;
                            $('.carousel-' + key).slick('slickAdd', addWork(work), lastSlidePos);
                        });
                    }
                });
            }
        });
    }
};
export default Carousel;
