var Carousel = {
    add: function(selector, a, b, c, d, e, f) {
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
    }
};

