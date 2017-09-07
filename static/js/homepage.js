var carousels;
$().ready(function(){
    
    carousels = {
        available: {
            limit: 12,
            page: 0
        }
    }

    $('.responsive').slick({
        dots: false,
        infinite: false,
        speed: 100,
        slidesToShow: 6,
        slidesToScroll: 5,
        responsive: [{
            breakpoint: 900,
            settings: {
                slidesToShow: 6,
                slidesToScroll: 5,
            }
        }, {
            breakpoint: 800,
            settings: {
                slidesToShow: 3,
                slidesToScroll: 3,
                infinite: false,
            }
        }, {
            breakpoint: 600,
            settings: {
                slidesToShow: 2,
                slidesToScroll: 2,
                infinite: false,                
            }
        }, {
            breakpoint: 480,
            settings: {
                slidesToShow: 1,
                slidesToScroll: 1,
                infinite: false,
            }
        }]
    });

    var carouselBookItem = {
        render: function(item) {
            return '<div class="book-carousel-item">' +
                '<img src="' + (item.cover_url || 'https://archive.org/services/img/' + item.ocaid) + '"/>' +
                '<button>Borrow</button>' +
                '<h1 class="book-carousel-item-title">' + item.title + '</h1>' +
                '</div>';
        }
    };


    var setupCarousel = function(name) {
        updateCarousel(name)
        $('.responsive').on('afterChange', function(e, slick, cur) {
            if (cur === slick.$slides.length - 1) {
                e.preventDefault()
                updateCarousel(name);
            }
        });
    }
    
    var updateCarousel = function(name) {
        carousels[name].page += 1;
        $.ajax({
            type: 'get',
            url: "/available?limit=" + carousels[name].limit + "&page=" + carousels[name].page,
            success: function(items) {
                for (var i in items) {
                    $('.responsive').slick('slickAdd', carouselBookItem.render(items[i]));
                }
                //$('.responsive').slick(items);
            }
        });
    }
    setupCarousel('available');



});
