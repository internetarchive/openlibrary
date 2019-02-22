// used in templates/covers/add.html
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

        $('.carousel-'+key).on('afterChange', function(e, slick, cur) {
            // console.log(slick.$slides.length);
            // console.log(cur);
            // console.log(e.currentSlide);
            // console.log(e.slideCount);
            if (cur === slick.$slides.length - 1)
             {
              //Use loadMoreUrl for loading more items
              $('.carousel-' + key).slick('slickAdd',
            '<div class="book carousel__item slick-slide slick-current slick-active" data-slick-index="0" aria-hidden="false" tabindex="-1" role="option" aria-describedby="slick-slide00" style="width: 128px;"> \
                <div class="book-cover"> \
                    <a href="/works/OL2950945W" tabindex="0"> \
                    <img class="bookcover" width="130" height="200" title="Comet by Carl Sagan" src="//covers.openlibrary.org/b/id/253762-M.jpg"> \
                    </a> \
                </div> \
                <div class="book-cta"><a class="btn primary " href="/books/OL1024614M/x/borrow" data-ol-link-track="subjects" title="Borrow eBook Comet" data-key="subjects" data-ocaid="comet00saga_1" tabindex="0">Borrow eBook</a></div> \
            </div>', $('.carousel-' + key).slick('slickCurrentSlide')-1);
              console.log("Load more called");
            //   cur = cur + 1;
            //   console.log(cur);
            }
          });
    }
};
export default Carousel;
