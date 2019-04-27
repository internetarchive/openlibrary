// used in templates/covers/add.html

const Carousel = {

    /**
     * function Carousel.add instantiates a new slick carousel and optionally
     * loadMore params for lazy-loading more pages of results on the fly
     * @param {string} selector to bind carousel
     * @param {string} a - f are number of items to render at different mobile breakpoints
     * @param {{ 
     *   url:string endpoint for fetching additional results
     *   getItems:function which extracts item values out of the API response
     *   addItem:function which consumes and item and returns html to add as a new slide
     *   limit:int number of slides to add when end is hit
     *   pageMode:string which specifies if API uses 'page' or 'offset' as its mechanism
     * }} loadMore is a dict of options for lazy-loading and includes:
     */
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

        // if a loadMore config is provided and it has a (required) url
        if (loadMore && loadMore.url) {
            var url;
            try {
                // exception handling needed in case loadMore.url is relative path
                url = new URL(loadMore.url);
            } catch (e) {
                url = new URL(window.location.origin + loadMore.url);
            }
            var default_limit = 18; // 3 pages of 6 items
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
                        url: url,
                        type: 'GET',
                        success: function(result) {
                            var items = loadMore.getItems(result)
                            $.each(items, function(item_index) {
                                var item = items[item_index];
                                var lastSlidePos = $(selector + '.slick-slider')
                                    .slick("getSlick").$slides.length - 1;
                                $(selector).slick('slickAdd', loadMore.addItem(item), lastSlidePos);
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
