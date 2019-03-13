// used in templates/covers/add.html
var slicker;
var Carousel = {
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

        var addWork = function(work) {
            console.log(work);
            return '<div class="book carousel__item slick-slide slick-active" aria-hidden="false" tabindex="-1" role="option" aria-describedby="slick-slide00" style="width: 128px;">' +
                '<div class="book-cover">' +
                  '<a href="' + work.key + '" tabindex="0">' +
                    '<img class="bookcover" width="130" height="200" title="' + work.title + '" ' +
                         'src="//covers.openlibrary.org/b/id/' + work.cover_id + '-M.jpg">' +
                  '</a>' +
                '</div>' +
                '<div class="book-cta">' + // needs to be computed based on availability
                  '<a class="btn primary " href="/books/OL1024614M/x/borrow" data-ol-link-track="subjects" ' +
                  'title="Borrow eBook Comet" data-key="subjects" data-ocaid="comet00saga_1" tabindex="0">Borrow</a>' +
                '</div>' +
              '</div>';
        }

        $('.carousel-'+key).on('afterChange', function(e, slick, cur) {
            var limit = slick.originalSettings.slidesToScroll;
            var offset = slick.slickCurrentSlide() + 1;

            var currentSlide = $('.slick-slider').slick('slickCurrentSlide');
            var currentSlideNumber = currentSlide + limit;
            var totalSlides = $('.slick-slider').slick("getSlick").$slides.length;

            if (currentSlideNumber >= totalSlides) {
                $.ajax({
                    'url': loadMoreUrl + '?offset=' + offset + '&limit=' + limit,
                    'type': 'GET',
                    success: function(subject_results) {
                        $.each(subject_results.works, function(work_idx) {
                            var work = subject_results.works[work_idx];
                            console.log(work);
                            var lastSlidePos = $('.slick-slider').slick("getSlick").$slides.length - 1;
                            $('.carousel-' + key).slick('slickAdd', addWork(work), lastSlidePos);
                        });
                    }
                });
            }
        });
    }
};
export default Carousel;
